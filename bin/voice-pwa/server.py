#!/usr/bin/env python3
"""Loopback Cartesia Ink hold-to-talk for Termix/Tailscale.

Binds 127.0.0.1:8787 only. API key stays on this host. Injects transcripts
into tmux session `mac` (not Cos).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("VOICE_PWA_HOST", "127.0.0.1")
PORT = int(os.environ.get("VOICE_PWA_PORT", "8787"))
TMUX_TARGET = os.environ.get("VOICE_PWA_TMUX", "mac:0.0")
STATIC = Path(__file__).resolve().parent / "static"
COS_ENV = Path.home() / ".local/share/hermes-agents/chief-of-staff/profiles/chief-of-staff/.env"
DEFAULT_BASE = "https://api.cartesia.ai"
API_VERSION = "2026-03-01"
STT_MODEL = os.environ.get("CARTESIA_STT_MODEL", "ink-2")


def _load_dotenv(path: Path) -> dict[str, str]:
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


def _secrets() -> dict[str, str]:
    env = dict(os.environ)
    env.update(_load_dotenv(COS_ENV))
    return env


def _stt(audio: bytes, content_type: str) -> dict[str, object]:
    secrets = _secrets()
    key = secrets.get("CARTESIA_API_KEY", "")
    if not key:
        return {"ok": False, "error": "CARTESIA_API_KEY missing on host"}
    base = (secrets.get("CARTESIA_STT_BASE_URL") or secrets.get("CARTESIA_BASE_URL") or DEFAULT_BASE).rstrip("/")
    suffix = ".webm"
    if "mp4" in content_type:
        suffix = ".mp4"
    elif "wav" in content_type:
        suffix = ".wav"
    elif "mpeg" in content_type or "mp3" in content_type:
        suffix = ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)
        tmp_path = tmp.name
    try:
        boundary = "----voicepwa"
        filename = Path(tmp_path).name
        file_body = Path(tmp_path).read_bytes()
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{STT_MODEL}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nen\r\n".encode(),
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n"
            ).encode()
            + file_body
            + b"\r\n"
            + f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(parts)
        req = urllib.request.Request(
            f"{base}/stt",
            data=body,
            method="POST",
            headers={
                "X-API-Key": key,
                "Cartesia-Version": API_VERSION,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"Cartesia STT HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}"}
    except Exception as exc:  # noqa: BLE001 — HTTP handler must not raise
        return {"ok": False, "error": f"Cartesia STT failed: {exc}"}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    text = payload.get("text", "") if isinstance(payload, dict) else ""
    return {"ok": True, "transcript": text or ""}


def _inject(text: str) -> dict[str, object]:
    cleaned = text.replace("\r", " ").strip()
    if not cleaned:
        return {"ok": False, "error": "empty transcript"}
    # Literal keys into the live mac pane only. Never Cos.
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_TARGET, "-l", "--", cleaned],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_TARGET, "Enter"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        return {"ok": False, "error": f"tmux inject failed: {err}"}
    return {"ok": True, "target": TMUX_TARGET}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        super().log_message(fmt, *args)

    def _json(self, code: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/manifest.json":
            self._file(STATIC / "manifest.json", "application/manifest+json")
            return
        if self.path == "/health":
            secrets = _secrets()
            self._json(
                200,
                {
                    "ok": True,
                    "listen": f"{HOST}:{PORT}",
                    "tmux": TMUX_TARGET,
                    "cartesia_key": "present" if secrets.get("CARTESIA_API_KEY") else "missing",
                },
            )
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        if self.path == "/stt":
            result = _stt(raw, self.headers.get("Content-Type") or "application/octet-stream")
            self._json(200 if result.get("ok") else 502, result)
            return
        if self.path == "/inject":
            try:
                body = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "invalid json"})
                return
            result = _inject(str(body.get("text") or ""))
            self._json(200 if result.get("ok") else 500, result)
            return
        self._json(404, {"ok": False, "error": "not found"})


def main() -> int:
    STATIC.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"voice-pwa listen {HOST}:{PORT} tmux={TMUX_TARGET}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
