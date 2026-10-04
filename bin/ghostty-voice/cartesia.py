"""Cartesia Ink STT + Sonic TTS. Key stays in the CoS env file."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Iterator

COS_ENV = Path.home() / ".local/share/hermes-agents/chief-of-staff/profiles/chief-of-staff/.env"
HERMES_ENV = Path.home() / ".hermes/.env"
DEFAULT_BASE = "https://api.cartesia.ai"
API_VERSION = "2026-03-01"
# Docs (2026-09): ink-2 is WebSocket-only. Batch POST /stt is ink-whisper only.
# https://docs.cartesia.ai/use-the-api/stt/compare-endpoints
STT_MODEL = os.environ.get("CARTESIA_STT_MODEL", "ink-2")
STT_STREAM_MODELS = {"ink-2", "ink-preview"}
STT_BATCH_MODEL = "ink-whisper"
SAMPLE_RATE = 16000
CHUNK_MS = 100
TTS_MODEL = os.environ.get("CARTESIA_TTS_MODEL", "sonic-3.5")
# Public Cos-voice default. Distinct dests must not reuse this id.
DEFAULT_COS_VOICE_ID = "f6141af3-5f94-418c-80ed-a45d450e7e2e"
COS_VOICE_DESTS = {"", "cos", "cos-voice", "chief", "caws", "brief"}
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

_voice_cache = ""


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("'").strip('"')
    return out


def secrets() -> dict[str, str]:
    env = dict(os.environ)
    env.update(load_dotenv(HERMES_ENV))
    env.update(load_dotenv(COS_ENV))
    return env


def key_status() -> str:
    return "present" if secrets().get("CARTESIA_API_KEY") else "missing"


def _base(secrets_map: dict[str, str]) -> str:
    return (
        secrets_map.get("CARTESIA_STT_BASE_URL")
        or secrets_map.get("CARTESIA_BASE_URL")
        or DEFAULT_BASE
    ).rstrip("/")


def _headers(key: str) -> dict[str, str]:
    version = secrets().get("CARTESIA_VERSION") or API_VERSION
    return {"X-API-Key": key, "Cartesia-Version": version}


def _suffix(content_type: str) -> str:
    if "mp4" in content_type or "m4a" in content_type or "aac" in content_type:
        return ".mp4"
    if "wav" in content_type:
        return ".wav"
    if "mpeg" in content_type or "mp3" in content_type:
        return ".mp3"
    if "ogg" in content_type:
        return ".ogg"
    return ".webm"


def _normalize_wav(audio: bytes, content_type: str) -> tuple[bytes, str] | dict[str, Any]:
    if len(audio) < 256:
        return {"ok": False, "error": "audio too short; hold longer or tap once to toggle"}
    suffix = _suffix(content_type)
    if suffix == ".wav" and audio[:4] == b"RIFF":
        return audio, "audio/wav"
    if not Path(FFMPEG).is_file():
        return audio, content_type or "application/octet-stream"
    src = dest = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio)
            src = tmp.name
        dest = src + ".wav"
        proc = subprocess.run(
            [FFMPEG, "-y", "-i", src, "-ac", "1", "-ar", "16000", "-f", "wav", dest],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0 or not Path(dest).is_file():
            return audio, content_type or "application/octet-stream"
        wav = Path(dest).read_bytes()
        if len(wav) < 256:
            return {"ok": False, "error": "audio too short after convert; hold longer"}
        return wav, "audio/wav"
    except Exception:  # noqa: BLE001 — fall back to original bytes
        return audio, content_type or "application/octet-stream"
    finally:
        for path in (src, dest):
            if path:
                Path(path).unlink(missing_ok=True)


def _pcm_from_wav(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), "rb") as handle:
        return handle.readframes(handle.getnframes())


def _ws_url(secrets_map: dict[str, str], model: str) -> str:
    http = urllib.parse.urlparse(_base(secrets_map))
    scheme = "wss" if http.scheme == "https" else "ws"
    query = urllib.parse.urlencode(
        {
            "model": model,
            "encoding": "pcm_s16le",
            "sample_rate": str(SAMPLE_RATE),
            "language": secrets_map.get("CARTESIA_LANGUAGE") or "en",
        }
    )
    return urllib.parse.urlunparse((scheme, http.netloc, "/stt/websocket", "", query, ""))


def _ws_frame(opcode: int, payload: bytes) -> bytes:
    mask = os.urandom(4)
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", n))
    header.extend(mask)
    return bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def _ws_read(sock: ssl.SSLSocket) -> tuple[int, bytes]:
    hdr = sock.recv(2)
    if len(hdr) < 2:
        raise ConnectionError("websocket closed")
    opcode = hdr[0] & 0x0F
    length = hdr[1] & 0x7F
    masked = bool(hdr[1] & 0x80)
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    mask = sock.recv(4) if masked else b""
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("websocket payload truncated")
        data += chunk
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def _ws_connect(url: str, headers: dict[str, str], timeout: float = 30) -> ssl.SSLSocket:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = [
        f"GET {parsed.path or '/'}?{parsed.query} HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    for name, value in headers.items():
        req.append(f"{name}: {value}")
    raw = socket.create_connection((host, port), timeout=timeout)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    sock.sendall(("\r\n".join(req) + "\r\n\r\n").encode())
    prelude = b""
    while b"\r\n\r\n" not in prelude:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("websocket handshake closed")
        prelude += chunk
    status = prelude.split(b"\r\n", 1)[0]
    if b" 101 " not in status:
        raise ConnectionError(f"websocket handshake failed: {status.decode('utf-8', 'replace')}")
    accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
    if accept not in prelude:
        raise ConnectionError("websocket accept mismatch")
    sock.settimeout(timeout)
    return sock


def _pcm_chunks(pcm: bytes) -> Iterator[bytes]:
    width = (SAMPLE_RATE * 2 * CHUNK_MS) // 1000
    if not pcm:
        return
    for i in range(0, len(pcm), width):
        yield pcm[i : i + width]


def _stt_batch(secrets_map: dict[str, str], audio: bytes, content_type: str, model: str) -> dict[str, Any]:
    key = secrets_map.get("CARTESIA_API_KEY", "")
    boundary = "----ghosttyvoice"
    filename = "talk.wav" if "wav" in content_type else "talk.bin"
    file_type = content_type or "application/octet-stream"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nen\r\n".encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {file_type}\r\n\r\n"
        ).encode()
        + audio
        + b"\r\n"
        + f"--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        f"{_base(secrets_map)}/stt",
        data=b"".join(parts),
        method="POST",
        headers={
            **_headers(key),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error": f"Cartesia STT HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}",
            "model": model,
            "endpoint": "stt-batch",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Cartesia STT failed: {exc}", "model": model, "endpoint": "stt-batch"}
    text = payload.get("text", "") if isinstance(payload, dict) else ""
    return {"ok": True, "transcript": text or "", "model": model, "endpoint": "stt-batch"}


def _stt_ink2(secrets_map: dict[str, str], wav: bytes, model: str) -> dict[str, Any]:
    """Push-to-talk path: Realtime STT (Manual) /stt/websocket. ink-2 only."""
    key = secrets_map.get("CARTESIA_API_KEY", "")
    try:
        pcm = _pcm_from_wav(wav)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"wav decode failed: {exc}", "model": model, "endpoint": "stt-websocket"}
    if len(pcm) < 320:
        return {"ok": False, "error": "audio too short; hold longer or tap once to toggle", "model": model}
    sock = None
    try:
        sock = _ws_connect(_ws_url(secrets_map, model), _headers(key), timeout=45)
        for chunk in _pcm_chunks(pcm):
            sock.sendall(_ws_frame(0x2, chunk))
            time.sleep(CHUNK_MS / 1000)
        sock.sendall(_ws_frame(0x1, b"finalize"))
        sock.sendall(_ws_frame(0x1, b"close"))
        transcript = ""
        deadline = time.time() + 45
        while time.time() < deadline:
            opcode, payload = _ws_read(sock)
            if opcode == 0x8:
                break
            if opcode == 0x9:
                sock.sendall(_ws_frame(0xA, payload))
                continue
            if opcode != 0x1:
                continue
            event = json.loads(payload.decode())
            kind = event.get("type")
            if kind == "transcript" and event.get("is_final"):
                transcript += str(event.get("text") or "")
            elif kind == "error":
                return {
                    "ok": False,
                    "error": f"Cartesia STT WS: {event.get('message') or event}",
                    "model": model,
                    "endpoint": "stt-websocket",
                }
            elif kind == "done":
                break
        return {
            "ok": True,
            "transcript": transcript,
            "model": model,
            "endpoint": "stt-websocket",
            "mode": "record-then-upload",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Cartesia STT WS failed: {exc}", "model": model, "endpoint": "stt-websocket"}
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


class Ink2Live:
    """Host-side Ink 2 session: stream PCM while the phone is held, finalize on release."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or STT_MODEL
        self.sock: ssl.SSLSocket | None = None
        self._lock = threading.Lock()
        self._done = threading.Event()
        self.partials: list[str] = []
        self.finals: list[str] = []
        self.error = ""
        self.bytes_sent = 0
        self.opened_at = 0.0
        self.last_chunk_at = 0.0
        self._reader: threading.Thread | None = None

    def last_partial(self) -> str:
        return self.partials[-1] if self.partials else ""

    def open(self) -> dict[str, Any]:
        secrets_map = secrets()
        key = secrets_map.get("CARTESIA_API_KEY", "")
        if not key:
            return {"ok": False, "error": "CARTESIA_API_KEY missing on host"}
        try:
            self.sock = _ws_connect(_ws_url(secrets_map, self.model), _headers(key), timeout=45)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"Cartesia STT WS failed: {exc}",
                "model": self.model,
                "endpoint": "stt-websocket",
            }
        self.opened_at = time.time()
        self.last_chunk_at = self.opened_at
        self._reader = threading.Thread(target=self._read_loop, name="ink2-live", daemon=True)
        self._reader.start()
        return {
            "ok": True,
            "model": self.model,
            "endpoint": "stt-websocket",
            "mode": "stream-while-hold",
        }

    def send_pcm(self, pcm: bytes) -> dict[str, Any]:
        if self._done.is_set() and self.error:
            return {"ok": False, "error": f"Cartesia STT WS: {self.error}", "model": self.model}
        with self._lock:
            sock = self.sock
            if sock is None:
                return {"ok": False, "error": "stt session not open", "model": self.model}
            if pcm:
                width = (SAMPLE_RATE * 2 * CHUNK_MS) // 1000
                try:
                    for i in range(0, len(pcm), width or len(pcm)):
                        sock.sendall(_ws_frame(0x2, pcm[i : i + width]))
                except OSError as exc:
                    self.error = str(exc)
                    self._done.set()
                    return {"ok": False, "error": f"Cartesia STT WS failed: {exc}", "model": self.model}
                self.bytes_sent += len(pcm)
                self.last_chunk_at = time.time()
        return {
            "ok": True,
            "bytes": len(pcm),
            "total": self.bytes_sent,
            "partial": self.last_partial(),
            "mode": "stream-while-hold",
        }

    def finalize(self) -> dict[str, Any]:
        with self._lock:
            sock = self.sock
            if sock is None:
                return {"ok": False, "error": "stt session not open", "model": self.model}
            if self.bytes_sent < 320:
                self.close()
                return {
                    "ok": False,
                    "error": "audio too short; hold longer or tap once to toggle",
                    "model": self.model,
                    "endpoint": "stt-websocket",
                    "mode": "stream-while-hold",
                }
            try:
                sock.sendall(_ws_frame(0x1, b"finalize"))
                sock.sendall(_ws_frame(0x1, b"close"))
            except OSError as exc:
                self.close()
                return {
                    "ok": False,
                    "error": f"Cartesia STT WS failed: {exc}",
                    "model": self.model,
                    "endpoint": "stt-websocket",
                }
        deadline = time.time() + 45
        while time.time() < deadline and not self._done.is_set():
            time.sleep(0.05)
        transcript = "".join(self.finals)
        err = self.error
        total = self.bytes_sent
        self.close()
        if err and not transcript:
            return {
                "ok": False,
                "error": f"Cartesia STT WS: {err}",
                "model": self.model,
                "endpoint": "stt-websocket",
                "mode": "stream-while-hold",
            }
        return {
            "ok": True,
            "transcript": transcript,
            "model": self.model,
            "endpoint": "stt-websocket",
            "mode": "stream-while-hold",
            "bytes": total,
        }

    def close(self) -> None:
        self._done.set()
        with self._lock:
            sock = self.sock
            self.sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _read_loop(self) -> None:
        sock = self.sock
        if sock is None:
            return
        while not self._done.is_set():
            try:
                sock.settimeout(0.3)
                opcode, payload = _ws_read(sock)
            except (TimeoutError, socket.timeout):
                continue
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
                self._done.set()
                return
            if opcode == 0x8:
                self._done.set()
                return
            if opcode == 0x9:
                try:
                    sock.sendall(_ws_frame(0xA, payload))
                except OSError as exc:
                    self.error = str(exc)
                    self._done.set()
                    return
                continue
            if opcode != 0x1:
                continue
            try:
                event = json.loads(payload.decode())
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "transcript":
                text = str(event.get("text") or "")
                if event.get("is_final"):
                    self.finals.append(text)
                elif text:
                    self.partials.append(text)
            elif kind == "error":
                self.error = str(event.get("message") or event)
                self._done.set()
                return
            elif kind == "done":
                self._done.set()
                return


def transcribe(audio: bytes, content_type: str) -> dict[str, Any]:
    secrets_map = secrets()
    key = secrets_map.get("CARTESIA_API_KEY", "")
    if not key:
        return {"ok": False, "error": "CARTESIA_API_KEY missing on host"}
    normalized = _normalize_wav(audio, content_type or "")
    if isinstance(normalized, dict):
        return normalized
    body, mime = normalized
    model = secrets_map.get("CARTESIA_STT_MODEL") or STT_MODEL
    if model in STT_STREAM_MODELS:
        result = _stt_ink2(secrets_map, body if mime == "audio/wav" else body, model)
        if result.get("ok"):
            return result
        fallback = _stt_batch(secrets_map, body, mime, STT_BATCH_MODEL)
        if fallback.get("ok"):
            fallback["fallback_from"] = model
            fallback["stream_error"] = result.get("error")
        return fallback
    return _stt_batch(secrets_map, body, mime, model)


def _dest_voice_env(secrets_map: dict[str, str], dest: str) -> str:
    name = (dest or "").split(":")[0].strip().lower().replace("-", "_")
    if not name:
        return ""
    return secrets_map.get(f"CARTESIA_VOICE_ID_{name.upper()}") or ""


def resolve_voice(
    secrets_map: dict[str, str],
    dest: str | None = None,
    voice_id: str | None = None,
) -> str:
    global _voice_cache
    if voice_id:
        return voice_id
    dest_name = (dest or "").split(":")[0].strip().lower()
    assigned = _dest_voice_env(secrets_map, dest_name)
    if assigned:
        return assigned
    default = secrets_map.get("CARTESIA_VOICE_ID") or ""
    if dest_name in COS_VOICE_DESTS:
        return default or DEFAULT_COS_VOICE_ID
    if dest_name and default and default != DEFAULT_COS_VOICE_ID:
        return default
    if _voice_cache and _voice_cache != DEFAULT_COS_VOICE_ID:
        return _voice_cache
    key = secrets_map.get("CARTESIA_API_KEY", "")
    if not key:
        return ""
    req = urllib.request.Request(
        f"{_base(secrets_map)}/voices?limit=20",
        method="GET",
        headers=_headers(key),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001
        return ""
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            found = str(row["id"])
            if dest_name not in COS_VOICE_DESTS and found == DEFAULT_COS_VOICE_ID:
                continue
            _voice_cache = found
            return _voice_cache
    return ""


def synthesize(text: str, dest: str | None = None, voice_id: str | None = None) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "error": "empty text"}
    secrets_map = secrets()
    key = secrets_map.get("CARTESIA_API_KEY", "")
    if not key:
        return {"ok": False, "error": "CARTESIA_API_KEY missing on host"}
    voice = resolve_voice(secrets_map, dest=dest, voice_id=voice_id)
    if not voice:
        return {"ok": False, "error": "Cartesia voice id missing and /voices returned none"}
    body: dict[str, Any] = {
        "model_id": secrets_map.get("CARTESIA_TTS_MODEL") or TTS_MODEL,
        "transcript": cleaned[:2000],
        "voice": {"mode": "id", "id": voice},
        "output_format": {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000},
    }
    language = secrets_map.get("CARTESIA_LANGUAGE")
    if language:
        body["language"] = language
    req = urllib.request.Request(
        f"{_base(secrets_map)}/tts/bytes",
        data=json.dumps(body).encode(),
        method="POST",
        headers={**_headers(key), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error": f"Cartesia TTS HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Cartesia TTS failed: {exc}"}
    if not audio:
        return {"ok": False, "error": "Cartesia TTS returned empty audio"}
    return {
        "ok": True,
        "audio_b64": base64.b64encode(audio).decode("ascii"),
        "mime": "audio/mpeg",
        "voice_id": voice,
        "dest": dest or "cos",
    }
