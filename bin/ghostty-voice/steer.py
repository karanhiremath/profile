"""Steer Cos via atop / Hermes inbox. Never tmux send-keys into Cos or Atop."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ATOP = shutil.which("atop") or str(Path.home() / ".local/bin/atop")
COS_HERMES_HOME = Path.home() / ".local/share/hermes-agents/chief-of-staff"
FALLBACK_HERMES_HOME = Path.home() / ".hermes"


def _cos_inbox_homes() -> list[Path]:
    """Write Cos steers only to the isolated chief-of-staff seat.

    ~/.hermes is a different profile tree (factory / project-manager) and
    must not receive Cos inbox events or the two homes fight.
    """
    try:
        from alias_seat import inbox_homes
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hermes"))
        from alias_seat import inbox_homes  # type: ignore
    homes = [path for path in inbox_homes("chief-of-staff") if path.exists() or path.parent.exists()]
    if homes:
        return homes
    if COS_HERMES_HOME.exists():
        return [COS_HERMES_HOME]
    return [COS_HERMES_HOME]


# Profile identity only. Never a tmux pane (`tmux:cos:0.0` / `this:0.0`).
DEFAULT_SID = "hermes:chief-of-staff"
COS_TUI_JSON = (
    Path.home() / ".local/share/hermes-agents/chief-of-staff/profiles/chief-of-staff/herm/tui.json"
)
VOICE_REPLY_DIR = Path.home() / ".local/share/ghostty-voice/replies"
REPLY_ENDPOINT = "http://127.0.0.1:8787/reply"
WORK_SESSIONS = tuple(f"ao{i}" for i in range(5)) + tuple(f"infra{i}" for i in range(5))
PLAN_SESSIONS = tuple(f"cos-ao{i}" for i in range(5)) + tuple(f"cos-infra{i}" for i in range(5))
COS_DESTS = {"cos", "cos-voice"}
COS_ALIASES = {
    "cos",
    "coz",
    "caws",
    "kaws",
    "kos",
    "cosie",
    "cocie",
    "cos-voice",
    "chief",
    "chief-of-staff",
    "c-o-s",
    "c.o.s",
    "c-o-s.",
}
COS_PHRASE = re.compile(
    r"\b(c[\s.\-]*o[\s.\-]*s|chief(?:\s+of\s+staff)?|caws|kaws|coz|cosie|cocie|kos|cos)\b",
    re.IGNORECASE,
)
PI_DESTS = {"this", "pi"}
CLAUDE_DESTS = {"claude"}
HERM_TUI = {"pm", "pl", "notes", "chief"}
BLOCKED_PERSONAL = {"cosw", "chief-of-staff-work", "cos-work"}
LANE_TOKEN = re.compile(
    r"\b(ao[0-4]|infra[0-4]|cos-ao[0-4]|cos-infra[0-4]|claude|pm|pl|notes|chief|cosw)\b",
    re.IGNORECASE,
)
BUFFER_CUES = ("into the buffer", "congress", "edit the prompt", "draft")
BUFFER_INDEX = Path.home() / ".pi/agent/buffers/INDEX.jsonl"
BRIEF_CUES = (
    "status",
    "summary",
    "summarize",
    "fleet",
    "lanes",
    "what's going",
    "whats going",
    "what is going",
    "what changed",
    "brief",
    "update me",
)


def is_brief_request(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(cue in lowered for cue in BRIEF_CUES)


def dest_kind(dest: str) -> str:
    name = canonicalize_dest(dest)
    if name in BLOCKED_PERSONAL:
        return "unknown"
    if name in COS_DESTS:
        return "cos"
    if name in PI_DESTS:
        return "pi"
    if name in CLAUDE_DESTS:
        return "claude"
    if name in HERM_TUI:
        return "herm_tui"
    if name in WORK_SESSIONS:
        return "work"
    if name in PLAN_SESSIONS:
        return "plan"
    if name == "brief":
        return "brief"
    return "unknown"


def canonicalize_dest(dest: str) -> str:
    raw = (dest or "").strip()
    if not raw:
        return ""
    name = raw.split(":")[0].strip()
    letters = re.sub(r"[^A-Za-z]", "", name)
    if letters.upper() == "COS":
        return "cos"
    folded = re.sub(r"[\s._]+", "-", name.lower())
    if folded in COS_ALIASES or folded.replace("-", "") in {"cos", "caws", "cosie", "cocie"}:
        return "cos"
    if name.lower() in {"chief", "cos-voice"}:
        return "cos"
    return name.lower()


def spoken_dest(dest: str) -> str:
    if dest_kind(dest) == "cos":
        return "Chief of Staff"
    name = canonicalize_dest(dest)
    return name or "the dest"


def is_buffer_request(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return bool(lowered) and any(cue in lowered for cue in BUFFER_CUES)


def named_dest(text: str) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    phrase = COS_PHRASE.search(cleaned)
    if phrase and canonicalize_dest(phrase.group(1)) == "cos":
        return "cos"
    start = re.match(
        r"^(this|pi|claude|pm|pl|notes|chief|cosw|caws|kaws|coz|cosie|cocie|ao[0-4]|infra[0-4]|cos-ao[0-4]|cos-infra[0-4])\b",
        cleaned,
        re.IGNORECASE,
    )
    if start:
        token = start.group(1).lower()
        if token in BLOCKED_PERSONAL:
            return token
        return canonicalize_dest(token)
    found = LANE_TOKEN.search(cleaned)
    if not found:
        return None
    token = found.group(1).lower()
    if token in BLOCKED_PERSONAL:
        return token
    return canonicalize_dest(token)


def compact_prompt(
    dest: str,
    transcript: str,
    fleet_note: str,
    *,
    sid: str = "",
    reply_id: str = "",
) -> str:
    note = (fleet_note or "").replace("\n", " ").strip()[:180]
    lines = [
        f"Voice steer dest={dest}.",
        f"Transcript: {(transcript or '').strip()}",
        f"Fleet: {note or 'n/a'}",
    ]
    if sid:
        lines.append(f"Sid: {sid}")
    if dest_kind(dest) == "cos" and reply_id:
        lines.append(
            f"Return the spoken reply to Cos-voice: POST {REPLY_ENDPOINT} "
            f'{{"id":"{reply_id}","text":"<reply>"}} or write steer-outbox/{reply_id}.json. '
            "No send-keys. Do not invent sids."
        )
    return "\n".join(lines)


def _run(argv: list[str], timeout: float = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _inbox_name(sid: str) -> str:
    body = (sid or "").replace("tmux:", "")
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in body)
    if looks_like_tmux_pane(sid) or looks_like_tmux_pane(body):
        return "chief-of-staff.jsonl"
    if safe.startswith("hermes-"):
        return f"{safe}.jsonl"
    return f"{safe or 'chief-of-staff'}.jsonl"


def _write_inbox(home: Path, sid: str, text: str, *, reply_id: str = "") -> Path:
    root = home / "steer-inbox"
    root.mkdir(parents=True, exist_ok=True)
    path = root / _inbox_name(sid)
    record = {
        "schema": "harness-steer.v1",
        "text": text,
        "mode": "steer",
        "sid": sid,
        "subagent_id": "",
        "ts": time.time(),
        "source": "ghostty-voice",
        "reply_id": reply_id,
        "reply_to": REPLY_ENDPOINT,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return path


def _atop_steer(text: str, sid: str, harness: str = "hermes") -> dict[str, Any] | None:
    if not Path(ATOP).is_file():
        return None
    proc = _run(
        [ATOP, "steer", "--harness", harness, "--sid", sid, "--text", text],
        timeout=12,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return {
            "ok": False,
            "delivered": False,
            "note": (proc.stderr or "atop steer produced no json").strip()[:240],
        }
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "delivered": False, "note": raw[:240]}
    return payload if isinstance(payload, dict) else None


def steer_cos(text: str, *, sid: str | None = None, reply_id: str = "") -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "delivered": False, "error": "empty steer text"}
    requested = (sid or os.environ.get("COS_VOICE_SID") or "").strip()
    if requested and reject_operator_sid("cos", requested) is None:
        target = requested
    else:
        target = resolve_cos_sid()
    written: list[str] = []
    inbox_ok = False
    for home in _cos_inbox_homes():
        try:
            path = _write_inbox(home, target, cleaned, reply_id=reply_id)
            written.append(str(path))
            inbox_ok = True
        except OSError as exc:
            written.append(f"{home}: {exc}")
    atop = None
    if reject_operator_sid("cos", target) is None:
        atop = _atop_steer(cleaned, target, harness="hermes")
    delivered = bool(atop and atop.get("delivered"))
    note = (atop or {}).get("note") if atop else ""
    if inbox_ok and not delivered:
        note = note or "persisted Cos steer inbox; Hermes HTTP not live so atop delivered=false"
    return {
        "ok": inbox_ok or delivered,
        "delivered": delivered or inbox_ok,
        "inbox_ok": inbox_ok,
        "sid": target,
        "reply_id": reply_id,
        "transport": "hermes-inbox" if not delivered else (atop or {}).get("transport") or "atop-steer",
        "effective": "inbox-persist" if not delivered else (atop or {}).get("effective"),
        "atop": atop,
        "inbox": written,
        "note": note or "Cos inbox persist",
    }


def steer_harness(text: str, *, sid: str, harness: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "delivered": False, "error": "empty steer text", "sid": sid}
    atop = _atop_steer(cleaned, sid, harness=harness)
    if atop is None:
        return {
            "ok": False,
            "delivered": False,
            "sid": sid,
            "harness": harness,
            "transport": "atop-steer",
            "note": "atop binary missing",
        }
    atop.setdefault("sid", sid)
    atop.setdefault("harness", harness)
    return atop


def resolve_sid(session: str) -> str:
    name = (session or "").split(":")[0].strip()
    if not name:
        return resolve_cos_sid()
    if name in COS_DESTS:
        return resolve_cos_sid()
    if name in WORK_SESSIONS:
        return f"tmux:{name}:0.0"
    if name in HERM_TUI:
        return name
    try:
        import fleet

        for row in (fleet.atop_sessions() or []):
            sid = str(row.get("sid") or "")
            tmux = str(row.get("tmux_target") or "")
            if sid.startswith(f"tmux:{name}:") or tmux.startswith(f"{name}:"):
                resolved = sid if sid.startswith("tmux:") else f"tmux:{tmux}"
                if name in WORK_SESSIONS or name in PLAN_SESSIONS:
                    return resolved
    except Exception:  # noqa: BLE001 — dump is optional for routing
        pass
    if name in PLAN_SESSIONS:
        return f"tmux:{name}:1.0"
    if dest_kind(name) in {"pi", "claude", "herm_tui", "cos"}:
        return name
    return f"tmux:{name}:0.0"


def steer_plan(text: str, session: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "delivered": False, "error": "empty steer text"}
    sid = resolve_sid(session)
    atop = steer_harness(cleaned, sid=sid, harness="claude-code")
    delivered = bool(atop.get("delivered"))
    return {
        "ok": True,
        "delivered": delivered,
        "sid": sid,
        "transport": (atop.get("transport") or "atop-steer") if delivered else "inbox",
        "effective": atop.get("effective") or ("between-turn" if delivered else "inbox-persist"),
        "atop": atop,
        "note": atop.get("note") or "plan lane inbox/atop only; no send-keys",
    }


def delivery(target: str, transport: str, ok: bool, note: str = "") -> dict[str, Any]:
    return {
        "target": target,
        "transport": transport,
        "ok": bool(ok),
        "note": (note or "")[:240],
    }


def steer_pi(text: str, *, sid: str | None = None) -> dict[str, Any]:
    target = sid or os.environ.get("COS_VOICE_PI_SID") or ""
    if not target:
        return {
            "ok": False,
            "delivered": False,
            "sid": "",
            "harness": "pi",
            "transport": "atop-steer-pi",
            "note": "pi dest needs target=sid; do not invent this:0.0",
        }
    if target.startswith("this:") or target == "this":
        return {
            "ok": False,
            "delivered": False,
            "sid": target,
            "harness": "pi",
            "transport": "atop-steer-pi",
            "note": "pi dest needs target=sid; do not invent this:0.0",
        }
    return steer_harness(text, sid=target, harness="pi")


def steer_claude(text: str, *, sid: str | None = None) -> dict[str, Any]:
    target = sid or "tmux:claude:0.0"
    return steer_harness(text, sid=target, harness="claude-code")


def steer_herm_tui(text: str, profile: str) -> dict[str, Any]:
    name = canonicalize_dest(profile)
    if name in BLOCKED_PERSONAL:
        return {
            "ok": False,
            "delivered": False,
            "error": "cosw blocked on personal Cos-voice",
            "sid": name,
        }
    if name in COS_DESTS or name == "cos":
        return steer_cos(text)
    sid = resolve_sid(name)
    written: list[str] = []
    for home in _cos_inbox_homes():
        try:
            written.append(str(_write_inbox(home, sid, text)))
        except OSError as exc:
            written.append(f"{home}: {exc}")
    atop = _atop_steer(text, sid, harness="hermes")
    if not (atop and atop.get("delivered")):
        atop_tui = _atop_steer(text, sid, harness="herm-tui")
        if atop_tui and atop_tui.get("delivered"):
            atop = atop_tui
    delivered = bool(atop and atop.get("delivered"))
    return {
        "ok": True,
        "delivered": delivered,
        "sid": sid,
        "transport": "hermes-inbox" if not delivered else (atop or {}).get("transport") or "atop-steer",
        "atop": atop,
        "inbox": written,
        "note": (atop or {}).get("note") or "herm-tui inbox persist; no send-keys",
    }


def looks_like_tmux_pane(value: str) -> bool:
    """True for `ao2:0.0` / `tmux:cos:2.7`. False for Hermes/cdev sids."""
    trimmed = (value or "").strip()
    if not trimmed:
        return False
    body = trimmed[5:] if trimmed.startswith("tmux:") else trimmed
    parts = body.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False
    xy = parts[1].split(".")
    if len(xy) != 2 or not xy[0] or not xy[1]:
        return False
    return xy[0].isdigit() and xy[1].isdigit()


def reject_operator_sid(kind: str, sid: str) -> str | None:
    """Pane-shaped values are not Cos / pi / herm-tui sids."""
    token = (sid or "").strip()
    if kind == "pi" and (not token or token in {"this", "pi"} or looks_like_tmux_pane(token)):
        return "pi dest needs target=sid; do not invent this:0.0"
    if kind in {"cos", "herm_tui"} and (not token or looks_like_tmux_pane(token)):
        return "pane address is not a hermes sid"
    return None


def resolve_cos_sid() -> str:
    """Live Cos identity only. Env and herm-tui lastSessionId; never invent a pane."""
    env = (os.environ.get("COS_VOICE_SID") or "").strip()
    if env and reject_operator_sid("cos", env) is None:
        return env
    try:
        data = json.loads(COS_TUI_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    live = str((data or {}).get("lastSessionId") or "").strip()
    if live and reject_operator_sid("cos", live) is None:
        return live
    return DEFAULT_SID


def _reply_paths(reply_id: str) -> list[Path]:
    ident = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in (reply_id or "latest"))
    paths = [VOICE_REPLY_DIR / f"{ident}.json", VOICE_REPLY_DIR / "latest.json"]
    for home in _cos_inbox_homes():
        root = home / "steer-outbox"
        paths.append(root / f"{ident}.json")
        paths.append(root / "latest.json")
    return paths


def write_reply(text: str, *, reply_id: str = "", dest: str = "cos") -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "error": "empty reply text", "id": reply_id}
    ident = (reply_id or "").strip() or f"reply-{int(time.time() * 1000)}"
    record = {
        "schema": "cos-voice-reply.v1",
        "id": ident,
        "dest": canonicalize_dest(dest) or "cos",
        "text": cleaned,
        "ts": time.time(),
        "source": "ghostty-voice",
    }
    written: list[str] = []
    ok = False
    for path in _reply_paths(ident):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            written.append(str(path))
            ok = True
        except OSError as exc:
            written.append(f"{path}: {exc}")
    return {
        "ok": ok,
        "id": ident,
        "dest": record["dest"],
        "paths": written,
        "note": "cos-voice reply outbox",
    }


def read_reply(reply_id: str = "") -> dict[str, Any] | None:
    seen: set[str] = set()
    latest: dict[str, Any] | None = None
    for path in _reply_paths(reply_id or "latest"):
        key = str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        try:
            rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        except (OSError, json.JSONDecodeError, IndexError):
            continue
        if not isinstance(rec, dict) or not str(rec.get("text") or "").strip():
            continue
        if reply_id and str(rec.get("id") or "") != reply_id:
            continue
        latest = rec
    return latest


def wait_reply(reply_id: str, *, timeout: float = 2.5, since: float = 0.0) -> dict[str, Any] | None:
    deadline = time.time() + max(0.2, timeout)
    while time.time() < deadline:
        found = read_reply(reply_id)
        if found:
            ts = float(found.get("ts") or 0)
            if since and ts and ts < since:
                time.sleep(0.15)
                continue
            return found
        time.sleep(0.15)
    return None


def _hint_matches(session_hint: str, dest: str) -> bool:
    hint = (session_hint or "").strip()
    name = (dest or "").split(":")[0].strip().lower()
    if not hint or not name:
        return False
    hint_session = hint.split(":")[0].strip().lower()
    return hint_session == name


def buffer_preview(dest: str, *, last_text: str = "", limit: int = 48) -> dict[str, Any]:
    """Congress prompt.md tail, or the last steered line. Never secrets."""
    name = canonicalize_dest(dest) or (dest or "").split(":")[0]
    prompt = resolve_prompt(name)
    text = ""
    path = ""
    if name in WORK_SESSIONS:
        transport = "tmux-input-buffer"
    elif name in COS_DESTS or name in HERM_TUI or name in PI_DESTS or name in CLAUDE_DESTS:
        transport = "inbox"
    else:
        transport = "inbox"
    if prompt is not None:
        transport = "nvim-buffer"
        path = str(prompt)
        try:
            lines = prompt.read_text(encoding="utf-8").splitlines()
            text = "\n".join(lines[-limit:])
        except OSError:
            text = ""
    if not text.strip() and last_text.strip():
        text = last_text.strip()
    return {
        "ok": True,
        "dest": name,
        "transport": transport,
        "path": path,
        "text": text,
    }


def resolve_prompt(dest: str, index_path: Path | None = None) -> Path | None:
    path = index_path or BUFFER_INDEX
    if not path.is_file():
        return None
    latest: dict[str, Any] | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if _hint_matches(str(rec.get("session_hint") or ""), dest):
            latest = rec
    raw = str((latest or {}).get("path") or "")
    if not raw:
        return None
    prompt = Path(raw)
    return prompt if prompt.is_file() else None


def append_congress(dest: str, text: str, *, index_path: Path | None = None) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "delivered": False, "error": "empty text", "send_keys": False}
    prompt = resolve_prompt(dest, index_path)
    if prompt is None:
        return {
            "ok": False,
            "delivered": False,
            "dest": dest,
            "transport": "nvim-buffer",
            "send_keys": False,
            "sync": False,
            "commit": False,
            "note": "no open prompt.md for dest",
        }
    try:
        with prompt.open("a", encoding="utf-8") as fh:
            fh.write("\n" + cleaned + "\n")
    except OSError as exc:
        return {
            "ok": False,
            "delivered": False,
            "dest": dest,
            "transport": "nvim-buffer",
            "send_keys": False,
            "error": str(exc)[:240],
        }
    return {
        "ok": True,
        "delivered": True,
        "dest": dest,
        "path": str(prompt),
        "transport": "nvim-buffer",
        "send_keys": False,
        "sync": False,
        "commit": False,
        "note": "appended prompt.md; no send-keys; no buffer sync",
    }
