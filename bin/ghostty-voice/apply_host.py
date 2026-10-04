"""Optional edge to ao2's cos-voice-wasm crate.

Does not edit the crate. Does not bind :8787. If ao2's host is already on
127.0.0.1:8788, prefer that HTTP sidecar; otherwise call the existing
`cos-voice-host` binary. Python fallback stays in lanes.py.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

PROFILE_BIN = Path(__file__).resolve().parents[1]
CRATE_HOST = PROFILE_BIN / "cos-voice-wasm" / "target" / "debug" / "cos-voice-host"
SIDECAR_HOST = os.environ.get("COS_VOICE_WASM_HOST", "127.0.0.1")
SIDECAR_PORT = int(os.environ.get("COS_VOICE_WASM_PORT", "8788"))
SIDECAR = f"{SIDECAR_HOST}:{SIDECAR_PORT}"


def host_bin() -> str | None:
    env = os.environ.get("COS_VOICE_HOST_BIN")
    if env and Path(env).is_file():
        return env
    if CRATE_HOST.is_file() and os.access(CRATE_HOST, os.X_OK):
        return str(CRATE_HOST)
    found = shutil.which("cos-voice-host")
    return found


def sidecar_up() -> bool:
    if SIDECAR_HOST not in {"127.0.0.1", "localhost"}:
        return False
    try:
        with socket.create_connection((SIDECAR_HOST, SIDECAR_PORT), timeout=0.15):
            return True
    except OSError:
        return False


def status() -> dict[str, Any]:
    binary = host_bin()
    up = sidecar_up()
    if up:
        via = "http"
    elif binary:
        via = "cli"
    else:
        via = "python-fallback"
    return {
        "ok": True,
        "crate": "cos-voice-wasm",
        "bin": binary or "",
        "sidecar": SIDECAR,
        "sidecar_up": up,
        "via": via,
        "replaced_8787": False,
    }


def _http(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 0.8) -> dict[str, Any] | None:
    if not sidecar_up():
        return None
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = Request(f"http://{SIDECAR}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except URLError:
        return None
    except TimeoutError:
        return None
    try:
        parsed = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _cli(argv: list[str], timeout: float = 2.0) -> dict[str, Any] | None:
    binary = host_bin()
    if not binary:
        return None
    proc = subprocess.run(
        [binary, *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_view(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    view = payload.get("view")
    if isinstance(view, dict):
        view = view.get("name") or view.get("id")
    if view is not None:
        payload = {**payload, "view": str(view).lower()}
    return payload


def select_view(view: str, dest: str = "") -> dict[str, Any] | None:
    dest = dest or ""
    http = _http("POST", "/view", {"view": view, "dest": dest})
    if http is not None:
        return _normalize_view(http)
    cli = _cli(["view", view, "--dest", dest or "ao2"])
    if cli is not None:
        return _normalize_view(cli)
    applied = _cli(["apply", json.dumps({"op": "view", "view": view, "dest": dest})])
    return _normalize_view(applied)


def allow(dest: str) -> dict[str, Any] | None:
    http = _http("POST", "/apply", {"op": "dest", "dest": dest})
    if http is not None:
        return http
    return _cli(["allow", dest])


def route(dest: str, text: str, mode: str | None = None) -> dict[str, Any] | None:
    body: dict[str, Any] = {"op": "route", "dest": dest, "text": text}
    if mode:
        body["mode"] = mode
    http = _http("POST", "/apply", body)
    if http is not None:
        return http
    argv = ["apply", json.dumps(body)]
    return _cli(argv)


def s2s(dest: str = "cos") -> dict[str, Any] | None:
    """Crate s2s plan only. Does not call Cartesia or replace :8787 TTS/STT."""
    body: dict[str, Any] = {"op": "s2s", "dest": dest}
    http = _http("POST", "/apply", body)
    if http is not None:
        return http
    http = _http("GET", f"/s2s?dest={dest}")
    if http is not None:
        return http
    return _cli(["apply", json.dumps(body)])


def buffer_append(dest: str, text: str) -> dict[str, Any] | None:
    cli = _cli(["buffer-append", "--dest", dest, "--text", text], timeout=3.0)
    if cli is not None:
        return cli
    return _http("POST", "/apply", {"op": "buffer", "dest": dest, "text": text})
