#!/usr/bin/env python3
"""Loopback Ghostty voice harness. Bind 127.0.0.1:8787 only."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import apply_host
import cartesia
import fleet
import lanes
import steer

HOST = os.environ.get("VOICE_PWA_HOST", "127.0.0.1")
PORT = int(os.environ.get("VOICE_PWA_PORT", "8787"))
STATIC = Path(__file__).resolve().parent / "static"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "target": "cos-voice",
    "lane": "cos-voice",
    "dest": "cos",
    "last_cue": "",
    "last_transcript": "",
    "last_partial": "",
    "last_brief": "",
    "stt_mode": "stream-while-hold",
    "stt_model": cartesia.STT_MODEL,
    "view": "pane",
    "pane_target": "cos:0.0",
    "frame_seq": 0,
    "reply_seq": 0,
    "reply_id": "",
    "last_audio_b64": "",
    "last_audio_mime": "",
}

_stt_lock = threading.Lock()
_stt_live: dict[str, cartesia.Ink2Live] = {}
_STT_IDLE_S = 90.0


_brief_at = 0.0


def _remember(transcript: str, dest: str | None = None, target: str | None = None) -> None:
    with _lock:
        _state["last_transcript"] = transcript
        if dest:
            _state["dest"] = dest
        if target and not lanes.inject_blocked(target):
            _state["target"] = target
            _state["lane"] = lanes.session_name(target)


def _brief(force: bool = False) -> str:
    global _brief_at
    with _lock:
        cached = str(_state.get("last_brief") or "")
    now = time.time()
    if cached and not force and now - _brief_at < 15:
        return cached
    spoken = fleet.spoken()
    with _lock:
        _state["last_brief"] = spoken
    _brief_at = now
    return spoken


def _stt_gc() -> None:
    now = time.time()
    with _stt_lock:
        stale = [
            sid
            for sid, live in _stt_live.items()
            if now - (live.last_chunk_at or live.opened_at or now) > _STT_IDLE_S
        ]
        for sid in stale:
            live = _stt_live.pop(sid, None)
            if live is not None:
                live.close()


def _stt_open() -> dict[str, Any]:
    _stt_gc()
    live = cartesia.Ink2Live()
    opened = live.open()
    if not opened.get("ok"):
        return opened
    sid = uuid.uuid4().hex
    with _stt_lock:
        _stt_live[sid] = live
    return {**opened, "session": sid}


def _stt_session(sid: str) -> cartesia.Ink2Live | None:
    with _stt_lock:
        return _stt_live.get(sid)


def _stt_drop(sid: str) -> cartesia.Ink2Live | None:
    with _stt_lock:
        return _stt_live.pop(sid, None)


def _stt_chunk(sid: str, pcm: bytes) -> dict[str, Any]:
    live = _stt_session(sid)
    if live is None:
        return {"ok": False, "error": "unknown stt session"}
    result = live.send_pcm(pcm)
    partial = str(result.get("partial") or live.last_partial() or "")
    if partial:
        with _lock:
            _state["last_partial"] = partial
            _state["last_cue"] = f"partial · {partial[:80]}"
    return result


def _stt_finalize(sid: str) -> dict[str, Any]:
    live = _stt_drop(sid)
    if live is None:
        return {"ok": False, "error": "unknown stt session"}
    result = live.finalize()
    if result.get("ok") and result.get("transcript"):
        with _lock:
            _state["last_transcript"] = str(result["transcript"])
            _state["last_partial"] = ""
    return result


def _stt_abort(sid: str) -> dict[str, Any]:
    live = _stt_drop(sid)
    if live is not None:
        live.close()
    return {"ok": True, "aborted": bool(live)}


def _apply_view(view: str, dest: str = "", target: str = "") -> dict[str, Any]:
    chosen = (target or dest or "").strip()
    watch = chosen or "cos"
    if view in {"pane", "ghostty", "tmux"} and lanes.watch_allowed(watch):
        selection = lanes.select_view("pane", watch)
    else:
        selection = apply_host.select_view(view, chosen) or lanes.select_view(view, chosen)
    if (
        view == "pane"
        and not selection.get("ok")
        and (not chosen or lanes.inject_blocked(chosen))
        and not lanes.watch_allowed(watch)
    ):
        fallback = lanes.first_live_worker()
        if fallback:
            selection = apply_host.select_view("pane", fallback) or lanes.select_view(
                "pane", fallback
            )
    if not selection.get("ok"):
        return selection
    with _lock:
        _state["view"] = str(selection["view"])
        if chosen:
            name = lanes.session_name(chosen)
            canon = steer.canonicalize_dest(name) if name else ""
            if canon and canon != "brief":
                _state["dest"] = canon
        if selection.get("pane_target"):
            pane_target = str(selection["pane_target"])
            _state["pane_target"] = pane_target
            if not lanes.inject_blocked(pane_target):
                _state["target"] = pane_target
                _state["lane"] = lanes.session_name(pane_target)
        elif chosen and not lanes.inject_blocked(chosen):
            _state["target"] = chosen if ":" in chosen else f"{lanes.session_name(chosen)}:0.0"
            _state["lane"] = lanes.session_name(chosen)
    return selection


def _deny_send_keys(target: str, need: str) -> dict[str, Any] | None:
    """Crate + Python deny Cos / Atop / cos-* before any tmux send-keys."""
    if lanes.inject_blocked(target):
        return {"ok": False, "error": f"blocked target {target}"}
    decision = apply_host.allow(target)
    if not decision:
        return None
    allowed = bool(decision.get("allow_pick") if need == "pick" else decision.get("allow_inject"))
    if allowed and decision.get("send_keys"):
        return None
    return {
        "ok": False,
        "error": str(decision.get("blocked_reason") or f"blocked target {target}"),
        "apply": "cos-voice-wasm",
    }


def _snapshot() -> dict[str, Any]:
    with _lock:
        target = str(_state["target"])
        lane = str(_state["lane"])
        dest = str(_state.get("dest") or "cos")
        view = str(_state.get("view") or "fleet")
        pane_target = str(_state.get("pane_target") or "")
        last_cue = str(_state["last_cue"])
        last_transcript = str(_state["last_transcript"])
        last_partial = str(_state.get("last_partial") or "")
        stt_mode = str(_state.get("stt_mode") or "stream-while-hold")
        stt_model = str(_state.get("stt_model") or cartesia.STT_MODEL)
        frame_seq = int(_state.get("frame_seq") or 0)
        reply_seq = int(_state.get("reply_seq") or 0)
        reply_id = str(_state.get("reply_id") or "")
    with _stt_lock:
        sessions = len(_stt_live)
    frame_target = pane_target or target
    pane = {"ok": False, "text": "", "error": ""}
    frame = {
        "ok": False,
        "view": "pane",
        "target": frame_target,
        "text": "",
        "plain": "",
        "blocked": True,
        "error": "",
        "seq": frame_seq,
        "cols": 0,
        "rows": 0,
    }
    if lanes.watch_allowed(frame_target):
        frame = lanes.capture_frame(frame_target, seq=frame_seq)
        pane = {
            "ok": bool(frame.get("ok")),
            "text": str(frame.get("plain") or frame.get("text") or ""),
            "error": str(frame.get("error") or ""),
        }
        with _lock:
            _state["frame_seq"] = int(frame.get("seq") or frame_seq)
    elif dest != "cos" and not lanes.inject_blocked(target):
        pane = lanes.capture_pane(target)
    brief = _brief()
    otel = fleet.otel_surface() if view == "otel" else {"ok": True, "cards": [], "alerts": []}
    pane_text = pane.get("text", "") if pane.get("ok") else (brief if view != "pane" else "")
    prompt = lanes.current_prompt(frame_target)
    buffer = steer.buffer_preview(dest, last_text=last_transcript)
    return {
        "ok": True,
        "listen": f"{HOST}:{PORT}",
        "lane": lane,
        "target": target,
        "dest": dest,
        "view": view,
        "views": list(lanes.SURFACE_VIEWS),
        "pane_target": frame_target if lanes.watch_allowed(frame_target) else "",
        "workers": lanes.worker_targets(),
        "last_cue": last_cue,
        "reply_seq": reply_seq,
        "reply_id": reply_id,
        "last_transcript": last_transcript,
        "last_partial": last_partial,
        "last_brief": brief,
        "cartesia_key": cartesia.key_status(),
        "stt_mode": stt_mode,
        "stt_model": stt_model,
        "stt_sessions": sessions,
        "lanes": lanes.catalog().get("lanes", []),
        "pane": pane_text,
        "pane_error": pane.get("error", ""),
        "apply": apply_host.status(),
        "frame": frame,
        "otel": otel,
        "prompt": prompt,
        "prompts": [prompt] if prompt else [],
        "buffer": buffer,
    }


def _handle_brief(transcript: str) -> dict[str, Any]:
    spoken = _brief(force=True)
    tts = cartesia.synthesize(spoken, dest="brief")
    _remember(transcript)
    result: dict[str, Any] = {
        "ok": True,
        "dest": "brief",
        "spoken": spoken,
        "deliveries": [],
        "transcript": transcript,
    }
    if tts.get("audio_b64"):
        result["audio_b64"] = tts["audio_b64"]
        result["mime"] = tts.get("mime") or "audio/mpeg"
    if not tts.get("ok"):
        result["note"] = tts.get("error") or "tts failed"
    return result


def _remember_audio(tts: dict[str, Any], *, reply_id: str = "", cue: str = "") -> None:
    with _lock:
        if cue:
            _state["last_cue"] = cue[:240]
        if tts.get("audio_b64"):
            _state["last_audio_b64"] = str(tts["audio_b64"])
            _state["last_audio_mime"] = str(tts.get("mime") or "audio/mpeg")
            _state["reply_seq"] = int(_state.get("reply_seq") or 0) + 1
            if reply_id:
                _state["reply_id"] = reply_id


def _accept_reply(text: str, *, reply_id: str = "", dest: str = "cos") -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "error": "empty reply text", "deliveries": []}
    stored = steer.write_reply(cleaned, reply_id=reply_id, dest=dest)
    ident = str(stored.get("id") or reply_id or "")
    tts = cartesia.synthesize(cleaned, dest=dest or "cos")
    _remember_audio(tts, reply_id=ident, cue="Chief of Staff reply")
    result: dict[str, Any] = {
        "ok": bool(stored.get("ok")),
        "id": ident,
        "dest": dest or "cos",
        "seq": int(_state.get("reply_seq") or 0),
        "deliveries": [
            steer.delivery(
                ident or dest or "cos",
                "cos-voice-reply",
                bool(stored.get("ok")),
                str(stored.get("note") or "cos-voice reply outbox"),
            )
        ],
    }
    if tts.get("audio_b64"):
        result["audio_b64"] = tts["audio_b64"]
        result["mime"] = tts.get("mime") or "audio/mpeg"
    elif not tts.get("ok"):
        result["note"] = tts.get("error") or "tts reply failed"
    return result


def _latest_reply_payload(reply_id: str = "") -> dict[str, Any]:
    with _lock:
        seq = int(_state.get("reply_seq") or 0)
        stored_id = str(_state.get("reply_id") or "")
        audio = str(_state.get("last_audio_b64") or "")
        mime = str(_state.get("last_audio_mime") or "")
    rec = steer.read_reply(reply_id or stored_id)
    result: dict[str, Any] = {
        "ok": bool(audio or rec),
        "id": str((rec or {}).get("id") or stored_id or reply_id or ""),
        "dest": str((rec or {}).get("dest") or "cos"),
        "seq": seq,
        "has_text": bool(rec and rec.get("text")),
    }
    if audio:
        result["audio_b64"] = audio
        result["mime"] = mime or "audio/mpeg"
    return result


def _deliver_cos(prompt: str, *, reply_id: str = "") -> dict[str, Any]:
    result = steer.steer_cos(prompt, reply_id=reply_id)
    inbox_ok = bool(result.get("ok") or result.get("inbox_ok"))
    return {
        **steer.delivery(
            str(result.get("sid") or steer.resolve_cos_sid()),
            str(result.get("transport") or "hermes-inbox"),
            inbox_ok,
            str(result.get("note") or "Cos inbox persist"),
        ),
        "sid": result.get("sid"),
        "reply_id": result.get("reply_id") or reply_id,
        "inbox_ok": inbox_ok,
        "atop_delivered": bool((result.get("atop") or {}).get("delivered")),
    }


def _deliver_work(prompt: str, session: str, target: str | None) -> list[dict[str, Any]]:
    pane = target or f"{session}:0.0"
    sid = f"tmux:{session}:0.0"
    atop = steer.steer_harness(prompt, sid=sid, harness="claude-code")
    injected = lanes.inject(prompt, pane)
    return [
        steer.delivery(
            sid,
            str(atop.get("transport") or "atop-steer"),
            bool(atop.get("delivered")),
            str(atop.get("note") or atop.get("error") or ""),
        ),
        steer.delivery(
            pane,
            "tmux-input-buffer",
            bool(injected.get("ok")),
            str(injected.get("error") or "sent prompt via tmux input-buffer"),
        ),
    ]


def _deliver_plan(prompt: str, session: str) -> dict[str, Any]:
    result = steer.steer_plan(prompt, session)
    return steer.delivery(
        str(result.get("sid") or session),
        str(result.get("transport") or "inbox"),
        bool(result.get("delivered")),
        str(result.get("note") or "plan inbox/atop only"),
    )


def _deliver_pi(prompt: str, target: str | None) -> dict[str, Any]:
    sid = None
    if target and lanes.session_name(target) not in {"this", "pi"}:
        candidate = target if target.startswith("tmux:") else target
        if steer.reject_operator_sid("pi", candidate) is None:
            sid = candidate
    result = steer.steer_pi(prompt, sid=sid)
    return steer.delivery(
        str(result.get("sid") or sid or ""),
        "atop-steer-pi",
        bool(result.get("delivered")),
        str(result.get("note") or result.get("error") or "pi atop-steer; no send-keys"),
    )


def _deliver_claude(prompt: str, target: str | None) -> dict[str, Any]:
    sid = None
    if target:
        session = lanes.session_name(target)
        sid = target if target.startswith("tmux:") else f"tmux:{session}:0.0"
    result = steer.steer_claude(prompt, sid=sid)
    return steer.delivery(
        str(result.get("sid") or sid or "tmux:claude:0.0"),
        "atop-steer-claude-code",
        bool(result.get("delivered")),
        str(result.get("note") or result.get("error") or "claude atop-steer; no send-keys"),
    )


def _deliver_herm_tui(prompt: str, profile: str) -> dict[str, Any]:
    result = steer.steer_herm_tui(prompt, profile)
    return steer.delivery(
        str(result.get("sid") or profile),
        str(result.get("transport") or "hermes-inbox"),
        bool(result.get("delivered") or result.get("ok")),
        str(result.get("note") or result.get("error") or "herm-tui inbox; no send-keys"),
    )


def _deliver_buffer(prompt: str, session: str) -> dict[str, Any]:
    crate = apply_host.buffer_append(session, prompt)
    result = crate if crate else steer.append_congress(session, prompt)
    return steer.delivery(
        str(result.get("path") or session),
        "nvim-buffer",
        bool(result.get("ok") or result.get("written") or result.get("delivered")),
        str(result.get("note") or result.get("error") or "congress prompt.md"),
    )


def _handle_voice(
    text: str,
    dest: str | None = None,
    target: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "error": "empty text", "dest": dest or "", "deliveries": [], "transcript": ""}
    with _lock:
        dest_in = (dest or str(_state.get("dest") or "cos")).strip() or "cos"
    target_in = (target or "").strip() or None
    mode_in = (mode or "").strip() or None
    if dest_in == "brief" or mode_in == "brief" or (
        steer.is_brief_request(cleaned) and not steer.is_buffer_request(cleaned) and mode_in != "buffer"
    ):
        return _handle_brief(cleaned)

    named = steer.named_dest(cleaned)
    route = named or dest_in
    route = steer.canonicalize_dest(route) or "cos"
    if route in steer.BLOCKED_PERSONAL or dest_in in steer.BLOCKED_PERSONAL:
        return {
            "ok": False,
            "error": "cosw blocked on personal Cos-voice",
            "dest": "cosw",
            "deliveries": [],
            "transcript": cleaned,
        }
    kind = steer.dest_kind(route)
    crate = apply_host.route(dest_in, cleaned, mode_in)
    if crate and crate.get("route"):
        routed = crate["route"]
        crate_dest = steer.canonicalize_dest(str(routed.get("dest") or route))
        crate_kind = str(routed.get("kind") or kind)
        if crate_dest and crate_kind.lower() not in {"unknown"}:
            route = crate_dest
            kind = crate_kind
        if routed.get("mode") == "buffer":
            mode_in = "buffer"
        if crate_dest in steer.BLOCKED_PERSONAL or crate_kind.lower() == "unknown" and crate_dest in steer.BLOCKED_PERSONAL:
            return {
                "ok": False,
                "error": "cosw blocked on personal Cos-voice",
                "dest": "cosw",
                "deliveries": [],
                "transcript": cleaned,
            }
    route = steer.canonicalize_dest(route) or "cos"
    kind = steer.dest_kind(route)
    if kind == "unknown":
        route = "cos"
        kind = "cos"
    reply_id = uuid.uuid4().hex[:12] if kind in {"cos", "Cos"} else ""
    cos_sid = steer.resolve_cos_sid() if kind in {"cos", "Cos"} else ""
    prompt = steer.compact_prompt(
        route,
        cleaned,
        fleet.one_line(),
        sid=cos_sid,
        reply_id=reply_id,
    )
    deliveries: list[dict[str, Any]] = []
    session = lanes.session_name(route) or route
    buffer = mode_in == "buffer" or steer.is_buffer_request(cleaned)

    if buffer and kind not in {"brief", "unknown"}:
        session = lanes.session_name(route) or route
        deliveries.append(_deliver_buffer(cleaned, session))
        _remember(cleaned, dest=session)
    elif kind == "work":
        session = lanes.session_name(route)
        deliveries.extend(_deliver_work(prompt, session, target_in))
        _remember(cleaned, dest=session, target=target_in or f"{session}:0.0")
    elif kind == "plan":
        session = lanes.session_name(route)
        deliveries.append(_deliver_plan(prompt, session))
        _remember(cleaned, dest=session)
    elif kind in {"cos", "Cos"}:
        deliveries.append(_deliver_cos(prompt, reply_id=reply_id))
        _remember(cleaned, dest="cos")
    elif kind in {"pi", "Pi"}:
        deliveries.append(_deliver_pi(prompt, target_in))
        _remember(cleaned, dest="pi")
    elif kind in {"claude", "Claude"}:
        deliveries.append(_deliver_claude(prompt, target_in))
        _remember(cleaned, dest="claude")
    elif kind in {"herm_tui", "hermtui", "HermTui"}:
        deliveries.append(_deliver_herm_tui(prompt, route))
        _remember(cleaned, dest=route)
    else:
        return {
            "ok": False,
            "error": f"unknown dest {route}",
            "dest": route,
            "deliveries": [],
            "transcript": cleaned,
        }

    if named and dest_in in {"cos", "cos-voice"} and named not in {"cos", "cos-voice"}:
        deliveries.append(_deliver_cos(prompt, reply_id=reply_id))

    dest_out = "cos" if steer.dest_kind(route) == "cos" else route
    ok_any = any(bool(item.get("ok")) for item in deliveries)
    spoken_reply = ""
    if dest_out == "cos" and reply_id:
        found = steer.wait_reply(reply_id, timeout=2.5)
        if found and str(found.get("text") or "").strip():
            spoken_reply = str(found["text"]).strip()
            deliveries.append(
                steer.delivery(
                    str(found.get("id") or reply_id),
                    "cos-voice-reply",
                    True,
                    "Cos voice-agent reply returned to :8787",
                )
            )
    who = steer.spoken_dest(dest_out)
    if spoken_reply:
        cue = spoken_reply
    elif dest_out == "cos":
        cue = (
            "Okay. Sent to Chief of Staff."
            if ok_any
            else "Chief of Staff inbox persist failed."
        )
    else:
        cue = f"Okay. Sent to {who}." if ok_any else f"Steer failed for {who}."
    result: dict[str, Any] = {
        "ok": True,
        "dest": dest_out,
        "sid": cos_sid or None,
        "spoken": cue if not spoken_reply else "Chief of Staff reply",
        "deliveries": deliveries,
        "transcript": cleaned,
        "reply_id": reply_id or None,
        "reply_seq": int(_state.get("reply_seq") or 0),
    }
    tts = cartesia.synthesize(cue, dest=dest_out)
    _remember_audio(tts, reply_id=reply_id, cue=result["spoken"])
    if tts.get("audio_b64"):
        result["audio_b64"] = tts["audio_b64"]
        result["mime"] = tts.get("mime") or "audio/mpeg"
    elif not tts.get("ok"):
        result["note"] = tts.get("error") or "tts cue failed"
    return result


def _layers() -> dict[str, Any]:
    snap = fleet.snapshot()
    spoken = fleet.spoken(snap)
    with _lock:
        _state["last_brief"] = spoken
    return fleet.phone_layers(snap, lanes.catalog(), lanes.worker_prompts())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        super().log_message(fmt, *args)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._json(404, {"ok": False, "error": "not found"})
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._file(STATIC / "app.js", "text/javascript; charset=utf-8")
            return
        if path == "/manifest.json":
            self._file(STATIC / "manifest.json", "application/manifest+json")
            return
        if path == "/icon.svg":
            self._file(STATIC / "icon.svg", "image/svg+xml")
            return
        if path.startswith("/vendor/"):
            rel = path[len("/vendor/") :]
            if not rel or ".." in rel.split("/"):
                self._json(404, {"ok": False, "error": "not found"})
                return
            vendor = (STATIC / "vendor" / rel).resolve()
            root = (STATIC / "vendor").resolve()
            if vendor != root and root not in vendor.parents:
                self._json(404, {"ok": False, "error": "not found"})
                return
            types = {
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".map": "application/json",
            }
            self._file(vendor, types.get(vendor.suffix, "application/octet-stream"))
            return
        if path == "/health":
            snap = _snapshot()
            self._json(
                200,
                {
                    "ok": True,
                    "listen": snap["listen"],
                    "cartesia_key": snap["cartesia_key"],
                    "lanes": snap["lanes"],
                    "target": snap["target"],
                    "lane": snap["lane"],
                    "dest": snap["dest"],
                    "view": snap["view"],
                    "views": snap["views"],
                    "pane_target": snap["pane_target"],
                    "stt_mode": snap["stt_mode"],
                    "stt_model": snap["stt_model"],
                    "stt_sessions": snap["stt_sessions"],
                    "apply": snap.get("apply") or apply_host.status(),
                },
            )
            return
        if path == "/view":
            query = parse_qs(parsed.query)
            wanted = (query.get("view") or [""])[0]
            dest = (query.get("dest") or query.get("target") or [""])[0]
            if wanted:
                selection = _apply_view(wanted, dest=dest)
                if not selection.get("ok"):
                    self._json(400, {**_snapshot(), **selection})
                    return
            self._json(200, _snapshot())
            return
        if path == "/reply":
            query = parse_qs(parsed.query)
            ident = (query.get("id") or [""])[0]
            payload = _latest_reply_payload(ident)
            self._json(200 if payload.get("ok") else 404, payload)
            return
        if path == "/otel":
            self._json(200, fleet.otel_surface())
            return
        if path == "/lanes":
            self._json(200, lanes.catalog())
            return
        if path == "/fleet":
            snap = fleet.snapshot()
            spoken = fleet.spoken(snap)
            with _lock:
                _state["last_brief"] = spoken
            self._json(200, {**snap, "spoken": spoken})
            return
        if path == "/layers":
            self._json(200, _layers())
            return
        if path == "/ghostty":
            self._json(200, lanes.ghostty_inventory())
            return
        if path == "/pane":
            query = parse_qs(parsed.query)
            with _lock:
                fallback = str(_state.get("pane_target") or _state["target"])
            target = (query.get("target") or [fallback])[0]
            if (query.get("esc") or ["0"])[0] in {"1", "true", "ansi"}:
                self._json(200, lanes.capture_frame(target))
                return
            self._json(200, lanes.capture_pane(target))
            return
        if path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    payload = json.dumps(_snapshot())
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        if self.path in {"/stt/open", "/stt/chunk", "/stt/finalize", "/stt/abort"}:
            sid = (self.headers.get("X-STT-Session") or "").strip()
            if self.path == "/stt/open":
                result = _stt_open()
                self._json(200 if result.get("ok") else 502, result)
                return
            if not sid:
                self._json(400, {"ok": False, "error": "missing X-STT-Session"})
                return
            if self.path == "/stt/chunk":
                result = _stt_chunk(sid, raw)
                self._json(200 if result.get("ok") else 502, result)
                return
            if self.path == "/stt/finalize":
                result = _stt_finalize(sid)
                self._json(200 if result.get("ok") else 502, result)
                return
            self._json(200, _stt_abort(sid))
            return
        if self.path == "/stt":
            result = cartesia.transcribe(raw, self.headers.get("Content-Type") or "application/octet-stream")
            if result.get("ok") and result.get("transcript"):
                with _lock:
                    _state["last_transcript"] = str(result["transcript"])
            self._json(200 if result.get("ok") else 502, result)
            return
        if self.path == "/reply":
            try:
                body = json.loads(raw.decode() or "{}") if raw else {}
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "invalid json"})
                return
            result = _accept_reply(
                str(body.get("text") or body.get("spoken") or ""),
                reply_id=str(body.get("id") or body.get("reply_id") or ""),
                dest=str(body.get("dest") or "cos"),
            )
            self._json(200 if result.get("ok") else 400, result)
            return
        if self.path == "/steer":
            try:
                body = json.loads(raw.decode() or "{}") if raw else {}
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "invalid json"})
                return
            result = _handle_voice(
                str(body.get("text") or ""),
                dest=str(body.get("dest") or "") or None,
                target=str(body.get("target") or "") or None,
                mode=str(body.get("mode") or "") or None,
            )
            err = str(result.get("error") or "")
            if result.get("ok"):
                code = 200
            elif err in {"empty text"} or err.startswith("unknown dest"):
                code = 400
            else:
                code = 500
            self._json(code, result)
            return
        if self.path == "/brief":
            spoken = _brief(force=True)
            tts = cartesia.synthesize(spoken, dest="brief")
            self._json(200 if tts.get("ok") else 502, {"ok": tts.get("ok"), "spoken": spoken, **tts})
            return
        try:
            body = json.loads(raw.decode() or "{}") if raw else {}
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        if self.path == "/tts":
            dest = str(body.get("dest") or _state.get("dest") or "cos")
            result = cartesia.synthesize(str(body.get("text") or ""), dest=dest)
            if result.get("ok"):
                with _lock:
                    _state["last_cue"] = str(body.get("text") or "")[:240]
            self._json(200 if result.get("ok") else 502, result)
            return
        if self.path == "/attach":
            result = lanes.attach_alias(str(body.get("alias") or ""))
            if result.get("ok") and result.get("session"):
                session = str(result["session"])
                with _lock:
                    _state["lane"] = session
                    if not lanes.inject_blocked(session):
                        _state["target"] = f"{session}:0.0"
            self._json(200 if result.get("ok") else 400, result)
            return
        if self.path == "/focus":
            session = str(body.get("session") or "")
            result = lanes.switch_session(session)
            if result.get("ok"):
                with _lock:
                    _state["lane"] = session
                    if not lanes.inject_blocked(session):
                        _state["target"] = f"{session}:0.0"
            self._json(200 if result.get("ok") else 400, result)
            return
        if self.path == "/inject":
            with _lock:
                target = str(body.get("target") or _state["target"])
            denied = _deny_send_keys(target, "inject")
            if denied:
                self._json(400, denied)
                return
            result = lanes.inject(str(body.get("text") or ""), target)
            if result.get("ok"):
                with _lock:
                    _state["target"] = target
                    _state["last_transcript"] = str(body.get("text") or "")
            err = str(result.get("error") or "")
            if result.get("ok"):
                code = 200
            elif "blocked" in err or err.startswith("empty"):
                code = 400
            else:
                code = 500
            self._json(code, result)
            return
        if self.path == "/pick":
            with _lock:
                fallback = str(_state["target"])
            target = str(body.get("target") or fallback)
            denied = _deny_send_keys(target, "pick")
            if denied:
                self._json(400, denied)
                return
            result = lanes.send_pick(str(body.get("key") or ""), target)
            self._json(200 if result.get("ok") else 400, result)
            return
        if self.path == "/view":
            selection = _apply_view(
                str(body.get("view") or ""),
                dest=str(body.get("dest") or ""),
                target=str(body.get("target") or ""),
            )
            snap = _snapshot()
            self._json(200 if selection.get("ok") else 400, {**snap, **selection})
            return
        self._json(404, {"ok": False, "error": "not found"})


def main() -> int:
    STATIC.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ghostty-voice listen {HOST}:{PORT} tmux={_state['target']}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
