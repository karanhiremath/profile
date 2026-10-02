"""Cartesia speech-to-text provider (Ink / ink-whisper).

Routes ``transcribe_audio`` calls when ``stt.provider: cartesia``. The
dispatcher passes ``model`` (from ``stt.cartesia.model``) and ``language``
(from ``stt.cartesia.language`` / ``stt.language``); both fall back to
provider defaults. Returns the standard ``{success, transcript, provider}``
envelope and never raises (per the TranscriptionProvider contract).

Cartesia docs (2026-09): ``ink-2`` / ``ink-preview`` are WebSocket-only
(``/stt/websocket``). Batch ``POST /stt`` is ``ink-whisper`` only. Cos TUI
voice records a WAV then calls this provider — batch on a stream model
hangs or returns empty, which is why native Cos Cartesia looked broken
while the Cos-voice PWA (websocket) worked.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import time
import urllib.parse
import wave
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import httpx

from agent.transcription_provider import TranscriptionProvider

from ._common import auth_headers, get_env, stt_base_url

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ink-preview"  # latest preview for CoS eval; override via stt.cartesia.model / CARTESIA_STT_MODEL
DEFAULT_LANGUAGE = "en"
STREAM_MODELS = {"ink-2", "ink-preview"}
BATCH_MODEL = "ink-whisper"
SAMPLE_RATE = 16000
CHUNK_MS = 100
HTTP_TIMEOUT = 30.0
WS_TIMEOUT = 45.0


def _fail(error: str, **extra: Any) -> Dict[str, Any]:
    payload = {
        "success": False,
        "transcript": "",
        "error": error,
        "provider": "cartesia",
    }
    payload.update(extra)
    return payload


def _ok(transcript: str, **extra: Any) -> Dict[str, Any]:
    payload = {
        "success": True,
        "transcript": transcript or "",
        "provider": "cartesia",
    }
    payload.update(extra)
    return payload


def _pcm_from_wav_bytes(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), "rb") as handle:
        return handle.readframes(handle.getnframes())


def _wav_bytes(path: str) -> Optional[bytes]:
    """Return 16 kHz mono WAV bytes, converting via ffmpeg when needed."""
    raw = Path(path).read_bytes()
    if raw[:4] == b"RIFF":
        try:
            with wave.open(path, "rb") as handle:
                channels = handle.getnchannels()
                rate = handle.getframerate()
                width = handle.getsampwidth()
            if channels == 1 and rate == SAMPLE_RATE and width == 2:
                return raw
        except wave.Error:
            pass
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg).is_file():
        return raw if raw[:4] == b"RIFF" else None
    dest = ""
    try:
        dest_fh = tempfile.NamedTemporaryFile(prefix="cartesia_stt_", suffix=".wav", delete=False)
        dest = dest_fh.name
        dest_fh.close()
        proc = subprocess.run(
            [ffmpeg, "-y", "-i", path, "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", dest],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0 or not Path(dest).is_file():
            return raw if raw[:4] == b"RIFF" else None
        converted = Path(dest).read_bytes()
        return converted if converted[:4] == b"RIFF" else None
    except Exception:  # noqa: BLE001 — fall back to original WAV if present
        return raw if raw[:4] == b"RIFF" else None
    finally:
        if dest:
            Path(dest).unlink(missing_ok=True)


def _ws_url(model: str, language: str) -> str:
    http = urllib.parse.urlparse(stt_base_url())
    scheme = "wss" if http.scheme == "https" else "ws"
    query = urllib.parse.urlencode(
        {
            "model": model,
            "encoding": "pcm_s16le",
            "sample_rate": str(SAMPLE_RATE),
            "language": language,
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


def _ws_connect(url: str, timeout: float = WS_TIMEOUT) -> ssl.SSLSocket:
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
    for name, value in auth_headers().items():
        req.append(f"{name}: {value}")
    raw = socket.create_connection((host, port), timeout=timeout)
    sock: ssl.SSLSocket | socket.socket
    if parsed.scheme == "wss":
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    else:
        sock = raw
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
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
    )
    if accept not in prelude:
        raise ConnectionError("websocket accept mismatch")
    sock.settimeout(timeout)
    return sock  # type: ignore[return-value]


def _pcm_chunks(pcm: bytes) -> Iterator[bytes]:
    width = (SAMPLE_RATE * 2 * CHUNK_MS) // 1000
    if not pcm:
        return
    for i in range(0, len(pcm), width):
        yield pcm[i : i + width]


def _transcribe_websocket(wav: bytes, model: str, language: str) -> Dict[str, Any]:
    try:
        pcm = _pcm_from_wav_bytes(wav)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"wav decode failed: {exc}", endpoint="stt-websocket", model=model)
    if len(pcm) < 320:
        return _fail("audio too short", endpoint="stt-websocket", model=model)
    sock = None
    try:
        sock = _ws_connect(_ws_url(model, language), timeout=WS_TIMEOUT)
        # Full WAV is already captured (Cos TUI PTT). Do not realtime-pace
        # 100ms chunks — that turns a 3s clip into a multi-second stall.
        for chunk in _pcm_chunks(pcm):
            sock.sendall(_ws_frame(0x2, chunk))
        sock.sendall(_ws_frame(0x1, b"finalize"))
        sock.sendall(_ws_frame(0x1, b"close"))
        transcript = ""
        deadline = time.time() + WS_TIMEOUT
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
                return _fail(
                    f"Cartesia STT WS: {event.get('message') or event}",
                    endpoint="stt-websocket",
                    model=model,
                )
            elif kind == "done":
                break
        return _ok(transcript, endpoint="stt-websocket", model=model)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"Cartesia STT WS failed: {exc}", endpoint="stt-websocket", model=model)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _transcribe_batch(file_path: str, model: str, language: str) -> Dict[str, Any]:
    data = {"model": model, "language": language}
    try:
        with open(file_path, "rb") as fh:
            files = {"file": (os.path.basename(file_path), fh, "application/octet-stream")}
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.post(
                    f"{stt_base_url()}/stt",
                    headers=auth_headers(),
                    data=data,
                    files=files,
                )
        if resp.status_code >= 400:
            return _fail(
                f"Cartesia STT HTTP {resp.status_code}: {resp.text[:500]}",
                endpoint="stt-batch",
                model=model,
            )
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — contract: never raise
        return _fail(f"Cartesia STT request failed: {exc}", endpoint="stt-batch", model=model)
    transcript = payload.get("text", "") if isinstance(payload, dict) else ""
    return _ok(transcript, endpoint="stt-batch", model=model)


class CartesiaTranscriptionProvider(TranscriptionProvider):
    @property
    def name(self) -> str:
        return "cartesia"

    @property
    def display_name(self) -> str:
        return "Cartesia"

    def is_available(self) -> bool:
        return bool(get_env("CARTESIA_API_KEY"))

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Cartesia",
            "badge": "paid",
            "tag": "Ink — streaming STT (ink-whisper)",
            "env_vars": [
                {
                    "key": "CARTESIA_API_KEY",
                    "prompt": "Cartesia API key",
                    "url": "https://play.cartesia.ai/console",
                },
            ],
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "ink-preview", "display": "Ink Preview (latest, websocket)"},
            {"id": "ink-2", "display": "Ink 2 (stable, websocket)"},
            {"id": "ink-whisper", "display": "Ink Whisper (batch POST /stt)"},
        ]

    def default_model(self) -> Optional[str]:
        return get_env("CARTESIA_STT_MODEL") or DEFAULT_MODEL

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        if not os.path.isfile(file_path):
            return _fail(f"audio file not found: {file_path}")

        model_id = model or self.default_model() or DEFAULT_MODEL
        lang = language or get_env("CARTESIA_LANGUAGE") or DEFAULT_LANGUAGE

        if model_id in STREAM_MODELS:
            wav = _wav_bytes(file_path)
            if wav:
                result = _transcribe_websocket(wav, model_id, lang)
                if result.get("success"):
                    return result
                logger.info("Cartesia stream STT failed (%s); falling back to %s", result.get("error"), BATCH_MODEL)
                fallback = _transcribe_batch(file_path, BATCH_MODEL, lang)
                if fallback.get("success"):
                    fallback["fallback_from"] = model_id
                    fallback["stream_error"] = result.get("error")
                    return fallback
                result["batch_error"] = fallback.get("error")
                return result
            logger.info("Cartesia stream STT skipped (no WAV); using batch %s", BATCH_MODEL)
            return _transcribe_batch(file_path, BATCH_MODEL, lang)

        return _transcribe_batch(file_path, model_id, lang)
