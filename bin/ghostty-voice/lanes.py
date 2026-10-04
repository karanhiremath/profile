"""AOS lane catalog + tmux / Ghostty / attach helpers.

Never invent workmux. Never send-keys into Cos / CosW / live atop panes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import zlib
from typing import Any

import apply_host

PROFILE_BIN = os.environ.get(
    "GHOSTTY_VOICE_PROFILE_BIN",
    str(__import__("pathlib").Path(__file__).resolve().parents[1]),
)
ATTACH_BIN = os.path.join(PROFILE_BIN, "tmux", "interactive")
SESH = shutil.which("sesh") or "/opt/homebrew/bin/sesh"
TMUX = shutil.which("tmux") or "/opt/homebrew/bin/tmux"
WORKER_SESSIONS = tuple(f"ao{i}" for i in range(5)) + tuple(f"infra{i}" for i in range(5))
SURFACE_VIEWS = ("fleet", "otel", "pane", "voices", "sessions")
PICK_KEYS = set("yYnN123456789") | {"Enter", "Escape", "esc"}
PROMPT_HINTS = (
    "Do you want",
    "❯",
    "permission",
    "[Y/n]",
    "[y/n]",
    "[yes/no]",
    "Allow this",
    "Do you want to",
)
_NUM_OPT = re.compile(r"^\s*(?:[❯▸>•-]\s*)?(\d+)[.)]\s+(\S.*)$")
_YN_HINT = re.compile(r"\[(?:Y/n|y/n|yes/?no)\]|Do you want|\bpermission\b", re.I)

LANES: list[dict[str, Any]] = [
    {"id": "ao0", "family": "data", "sessions": ["ao0", "cos-ao0"], "alias": "ao0", "kind": "sesh"},
    {"id": "ao1", "family": "model", "sessions": ["ao1", "cos-ao1"], "alias": "ao1", "kind": "sesh"},
    {"id": "ao2", "family": "harness", "sessions": ["ao2", "cos-ao2"], "alias": "ao2", "kind": "sesh"},
    {"id": "ao3", "family": "graph", "sessions": ["ao3", "cos-ao3"], "alias": "ao3", "kind": "sesh"},
    {"id": "ao4", "family": "fleet", "sessions": ["ao4", "cos-ao4"], "alias": "ao4", "kind": "sesh"},
    {
        "id": "infra",
        "family": "infra",
        "sessions": [f"infra{i}" for i in range(5)] + [f"cos-infra{i}" for i in range(5)],
        "alias": "infra0",
        "kind": "sesh",
    },
    {"id": "mac", "family": "host", "sessions": ["mac"], "alias": "mac", "kind": "attach"},
    {"id": "oma", "family": "peer", "sessions": ["home"], "alias": "oma-default", "kind": "attach"},
    {"id": "oma-s", "family": "sandbox", "sessions": [], "alias": "oma-s", "kind": "attach"},
    {"id": "mac-s", "family": "sandbox", "sessions": [], "alias": "mac-s", "kind": "attach"},
]

ATTACH_ALIASES = {
    "mac": ["mac"],
    "oma": ["oma-default"],
    "oma-default": ["oma-default"],
    "oma-s": ["oma-s"],
    "oma-default-s": ["oma-s"],
    "mac-s": ["mac-s"],
}

SESH_ALIASES = {
    "ao0": "ao0",
    "ao1": "ao1",
    "ao2": "ao2",
    "ao3": "ao3",
    "ao4": "ao4",
    "infra": "infra0",
    "infra0": "infra0",
    "infra1": "infra1",
    "infra2": "infra2",
    "infra3": "infra3",
    "infra4": "infra4",
    "mac": "mac",
    "notes": "notes",
    "pi-p": "pi-p",
    "tailscale": "tailscale",
}


def _run(argv: list[str], timeout: float = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def session_name(target: str) -> str:
    return (target or "").split(":")[0].strip()


def inject_blocked(target: str) -> bool:
    name = session_name(target)
    if not name:
        return True
    if name in {"cos", "atop"} or name.startswith("cos-") or name.startswith("atop"):
        return True
    if name in {"this", "pi", "pm", "pl", "notes", "claude", "chief", "cosw", "chief-of-staff-work"}:
        return True
    return False


def capture_allowed(target: str) -> bool:
    """Inject/pick frames: worker panes only. Cos / plan / atop stay send-keys blocked."""
    name = session_name(target)
    return bool(name) and name in WORKER_SESSIONS and not inject_blocked(name)


def watch_allowed(target: str) -> bool:
    """Display-only Cos + worker tails. Atop and plan panes stay blocked."""
    name = session_name(target)
    if not name or name.startswith("atop") or name.startswith("cos-"):
        return False
    if name == "cos":
        return True
    return capture_allowed(name)


def send_keys_allowed(target: str) -> bool:
    """Input-buffer / TUI pick only on worker panes. Never Cos, plan, Atop, or host."""
    return capture_allowed(target)


def parse_view(raw: str) -> str | None:
    token = (raw or "").strip().lower()
    if token in SURFACE_VIEWS:
        return token
    if token in {"metrics"}:
        return "otel"
    if token in {"ghostty", "tmux"}:
        return "pane"
    return None


def select_view(view: str, dest: str = "") -> dict[str, Any]:
    parsed = parse_view(view)
    if not parsed:
        return {
            "ok": False,
            "view": "fleet",
            "dest": dest,
            "pane_target": None,
            "error": f"unknown view {view}",
        }
    if parsed == "pane":
        watch = dest if dest else ("cos" if tmux_has("cos") else first_live_worker())
        if watch_allowed(watch):
            pane = watch if ":" in watch else f"{session_name(watch)}:0.0"
            return {
                "ok": True,
                "view": "pane",
                "dest": session_name(pane),
                "pane_target": pane,
                "error": None,
                "watch": True,
                "send_keys": send_keys_allowed(pane),
                "via": "watch",
            }
    crate_dest = dest
    if parsed == "pane" and (not dest or not capture_allowed(dest)):
        crate_dest = first_live_worker() or dest
    crate = apply_host.select_view(parsed, crate_dest or dest)
    if crate is not None:
        if crate.get("ok"):
            crate.setdefault("via", apply_host.status().get("via"))
            return crate
        if parsed != "pane":
            crate.setdefault("via", apply_host.status().get("via"))
            return crate
    if parsed in {"fleet", "otel"}:
        return {"ok": True, "view": parsed, "dest": dest, "pane_target": None, "error": None, "via": "python-fallback"}
    target = dest if dest else first_live_worker()
    if not capture_allowed(target):
        fallback = first_live_worker()
        if capture_allowed(fallback):
            target = fallback
        else:
            return {
                "ok": False,
                "view": "pane",
                "dest": dest,
                "pane_target": None,
                "error": f"pane view blocked on {target or dest or 'empty dest'}",
                "via": "python-fallback",
            }
    pane = target if ":" in target else f"{session_name(target)}:0.0"
    return {
        "ok": True,
        "view": "pane",
        "dest": session_name(pane),
        "pane_target": pane,
        "error": None,
        "via": "python-fallback",
    }


def first_live_worker() -> str:
    for session in WORKER_SESSIONS:
        if tmux_has(session):
            return f"{session}:0.0"
    return ""


def default_target(lane_id: str) -> str:
    for lane in LANES:
        if lane["id"] == lane_id:
            for sess in lane["sessions"]:
                if not inject_blocked(sess) and tmux_has(sess):
                    return f"{sess}:0.0"
            if lane["sessions"] and not inject_blocked(lane["sessions"][0]):
                return f"{lane['sessions'][0]}:0.0"
    return "mac:0.0"


def tmux_has(session: str) -> bool:
    proc = _run([TMUX, "has-session", "-t", session])
    return proc.returncode == 0


def tmux_sessions() -> list[dict[str, Any]]:
    proc = _run(
        [
            TMUX,
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_attached}\t#{session_windows}\t#{session_activity}",
        ]
    )
    if proc.returncode != 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rows.append(
            {
                "name": parts[0],
                "attached": parts[1] == "1" or parts[1] not in {"0", ""},
                "windows": int(parts[2] or 0),
                "activity": parts[3] if len(parts) > 3 else "",
                "blocked": inject_blocked(parts[0]),
            }
        )
    return rows


def tmux_clients() -> list[dict[str, str]]:
    proc = _run(
        [
            TMUX,
            "list-clients",
            "-F",
            "#{client_tty}\t#{client_session}\t#{client_termname}\t#{client_width}x#{client_height}",
        ]
    )
    if proc.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        out.append(
            {
                "tty": parts[0],
                "session": parts[1],
                "term": parts[2] if len(parts) > 2 else "",
                "size": parts[3] if len(parts) > 3 else "",
            }
        )
    return out


def pane_size(target: str) -> tuple[int, int]:
    proc = _run([TMUX, "display-message", "-t", target, "-p", "#{pane_width}\t#{pane_height}"])
    if proc.returncode != 0:
        return (0, 0)
    parts = (proc.stdout or "").strip().split("\t")
    try:
        return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else (0, 0)
    except ValueError:
        return (0, 0)


def capture_pane(target: str, lines: int = 80) -> dict[str, Any]:
    if not watch_allowed(target):
        return {"ok": False, "error": f"blocked target {target}", "text": ""}
    depth = max(1, min(int(lines), 200))
    proc = _run([TMUX, "capture-pane", "-t", target, "-p", "-J", "-S", f"-{depth}"])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "capture failed").strip()
        return {"ok": False, "error": err, "text": ""}
    return {"ok": True, "target": target, "text": proc.stdout}


def capture_frame(target: str, lines: int = 80, seq: int = 0) -> dict[str, Any]:
    """ANSI + plain pane frame for the Cos-voice xterm surface (Cos watch + workers)."""
    if not watch_allowed(target):
        return {
            "ok": False,
            "view": "pane",
            "target": target,
            "text": "",
            "plain": "",
            "blocked": True,
            "error": f"blocked target {target}",
            "seq": seq,
            "cols": 0,
            "rows": 0,
        }
    pane = target if ":" in target else f"{session_name(target)}:0.0"
    depth = max(1, min(int(lines), 200))
    ansi = _run([TMUX, "capture-pane", "-t", pane, "-p", "-e", "-S", f"-{depth}"])
    if ansi.returncode != 0:
        err = (ansi.stderr or ansi.stdout or "capture failed").strip()
        return {
            "ok": False,
            "view": "pane",
            "target": pane,
            "text": "",
            "plain": "",
            "blocked": False,
            "error": err,
            "seq": seq,
            "cols": 0,
            "rows": 0,
        }
    plain = _run([TMUX, "capture-pane", "-t", pane, "-p", "-J", "-S", f"-{depth}"])
    text = ansi.stdout or ""
    plain_text = plain.stdout if plain.returncode == 0 else text
    cols, rows = pane_size(pane)
    next_seq = zlib.crc32(text.encode("utf-8", "replace")) & 0xFFFFFFFF
    return {
        "ok": True,
        "view": "pane",
        "target": pane,
        "text": text,
        "plain": plain_text,
        "blocked": False,
        "error": None,
        "seq": next_seq or 1,
        "cols": cols,
        "rows": rows,
    }


def worker_targets() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "id": "cos",
            "target": "cos:0.0",
            "live": tmux_has("cos"),
            "family": "watch",
            "watch": True,
        }
    ]
    for session in WORKER_SESSIONS:
        live = tmux_has(session)
        rows.append(
            {
                "id": session,
                "target": f"{session}:0.0",
                "live": live,
                "family": "infra" if session.startswith("infra") else "work",
            }
        )
    return rows


def catalog() -> dict[str, Any]:
    live = {row["name"]: row for row in tmux_sessions()}
    lanes = []
    for lane in LANES:
        sessions = []
        for name in lane["sessions"]:
            info = live.get(name)
            if info:
                sessions.append({**info, "live": True, "blocked": inject_blocked(name)})
            else:
                sessions.append(
                    {
                        "name": name,
                        "attached": False,
                        "windows": 0,
                        "blocked": inject_blocked(name),
                        "live": False,
                    }
                )
        lanes.append(
            {
                "id": lane["id"],
                "family": lane["family"],
                "alias": lane["alias"],
                "kind": lane["kind"],
                "sessions": sessions,
                "inject": default_target(lane["id"]),
            }
        )
    return {"ok": True, "lanes": lanes, "clients": tmux_clients()}


def ghostty_inventory() -> dict[str, Any]:
    windows: list[dict[str, str]] = []
    script = (
        'tell application "System Events"\n'
        '  if not (exists process "Ghostty") then return ""\n'
        '  tell process "Ghostty"\n'
        "    set out to {}\n"
        "    repeat with w in windows\n"
        "      set end of out to (name of w as text)\n"
        "    end repeat\n"
        '    set AppleScript\'s text item delimiters to linefeed\n'
        "    return out as text\n"
        "  end tell\n"
        "end tell\n"
    )
    proc = _run(["osascript", "-e", script], timeout=6)
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            title = line.strip()
            if title:
                windows.append({"title": title})
    clients = [c for c in tmux_clients() if "ghostty" in (c.get("term") or "").lower()]
    return {
        "ok": True,
        "app": "Ghostty",
        "windows": windows,
        "tmux_clients": clients,
        "note": "Ghostty has no window/tab/split IPC; titles + tmux clients are best-effort.",
    }


def switch_session(session: str) -> dict[str, Any]:
    if not tmux_has(session):
        return {"ok": False, "error": f"no tmux session {session}"}
    switched = 0
    for client in tmux_clients():
        term = (client.get("term") or "").lower()
        # Leave desktop Ghostty on Cos / atop. Move Termix/phone clients only.
        if "ghostty" in term:
            continue
        proc = _run([TMUX, "switch-client", "-c", client["tty"], "-t", session])
        if proc.returncode == 0:
            switched += 1
    return {"ok": True, "session": session, "switched": switched}


def attach_alias(alias: str) -> dict[str, Any]:
    token = (alias or "").strip()
    if not token:
        return {"ok": False, "error": "empty alias"}
    parts = token.split()
    head = parts[0]
    extra = parts[1:]

    if head in SESH_ALIASES and head not in {"oma", "oma-default", "oma-s", "mac-s"}:
        session = extra[0] if extra else SESH_ALIASES[head]
        if inject_blocked(session):
            return {"ok": False, "error": f"blocked session {session}"}
        switched = switch_session(session)
        return {
            "ok": switched.get("ok", False),
            "alias": token,
            "session": session,
            "method": "tmux switch-client",
            "switched": switched.get("switched", 0),
            "error": switched.get("error"),
        }

    attach_args = ATTACH_ALIASES.get(head)
    if attach_args:
        argv = [ATTACH_BIN, *attach_args, *extra]
        # Detach from this HTTP process: open a new window on mac, never Cos.
        if tmux_has("mac"):
            proc = _run([TMUX, "new-window", "-t", "mac", "-n", f"attach-{head}", "--", *argv], timeout=12)
            if proc.returncode != 0:
                return {"ok": False, "alias": token, "error": (proc.stderr or proc.stdout).strip()}
            return {
                "ok": True,
                "alias": token,
                "session": extra[0] if extra else attach_args[-1],
                "method": "tmux new-window attach",
            }
        return {"ok": False, "error": "tmux session mac missing; cannot spawn attach"}

    if tmux_has(head) and not inject_blocked(head):
        switched = switch_session(head)
        return {
            "ok": switched.get("ok", False),
            "alias": token,
            "session": head,
            "method": "tmux switch-client",
            "switched": switched.get("switched", 0),
            "error": switched.get("error"),
        }
    return {"ok": False, "error": f"unknown alias {token}"}


def inject(text: str, target: str) -> dict[str, Any]:
    cleaned = text.replace("\r", " ").strip()
    if not cleaned:
        return {"ok": False, "error": "empty transcript"}
    if not send_keys_allowed(target):
        return {"ok": False, "error": f"blocked target {target}"}
    typed = _run([TMUX, "send-keys", "-t", target, "-l", "--", cleaned])
    if typed.returncode != 0:
        return {"ok": False, "error": f"tmux inject failed: {(typed.stderr or typed.stdout).strip()}"}
    entered = _run([TMUX, "send-keys", "-t", target, "Enter"])
    if entered.returncode != 0:
        return {"ok": False, "error": f"tmux enter failed: {(entered.stderr or entered.stdout).strip()}"}
    return {"ok": True, "target": target}


def send_pick(key: str, target: str) -> dict[str, Any]:
    token = (key or "").strip()
    if token in {"enter", "ENTER", "\n", "\r"}:
        token = "Enter"
    if token in {"esc", "ESC", "escape"}:
        token = "Escape"
    if token not in PICK_KEYS and token not in {"Enter", "Escape"}:
        return {"ok": False, "error": "key not allowed"}
    if token == "esc":
        token = "Escape"
    if not send_keys_allowed(target):
        return {"ok": False, "error": f"blocked target {target}"}
    proc = _run([TMUX, "send-keys", "-t", target, token])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout or "send-keys failed").strip()[:240]}
    return {"ok": True, "target": target, "key": token}


def parse_prompt(text: str, target: str = "") -> dict[str, Any] | None:
    """Read real TUI choices from a pane tail. No generic 1-9 pad."""
    raw = [ln.rstrip() for ln in (text or "").splitlines()]
    lines = [ln for ln in raw if ln.strip()][-24:]
    if not lines:
        return None
    blob = "\n".join(lines)
    choices: list[dict[str, str]] = []
    titles: list[str] = []
    for ln in lines:
        match = _NUM_OPT.match(ln)
        if match:
            key = match.group(1)
            label = match.group(2).strip()
            if key in set("123456789") and label:
                choices.append({"key": key, "label": label[:96]})
            continue
        stripped = ln.strip().lstrip("❯▸>•- ").strip()
        if "?" in stripped:
            titles.append(stripped)
    if choices:
        return {
            "target": target,
            "kind": "menu",
            "title": titles[-1] if titles else "Choose",
            "options": choices,
        }
    hinted = _YN_HINT.search(blob) or any(token in blob for token in PROMPT_HINTS)
    if not hinted:
        return None
    if "permission" in blob.lower() or _YN_HINT.search(blob) or "Do you want" in blob:
        return {
            "target": target,
            "kind": "confirm" if "permission" not in blob.lower() else "permission",
            "title": titles[-1] if titles else "Confirm",
            "options": [{"key": "y", "label": "Yes"}, {"key": "n", "label": "No"}],
        }
    return None


def _prompt_from_text(text: str, target: str) -> dict[str, Any] | None:
    return parse_prompt(text, target)


def current_prompt(target: str) -> dict[str, Any] | None:
    """Pick overlay only for worker panes that can take a key."""
    if not send_keys_allowed(target):
        return None
    cap = capture_pane(target, lines=24)
    if not cap.get("ok"):
        return None
    return parse_prompt(str(cap.get("text") or ""), target)


def worker_prompts() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for session in WORKER_SESSIONS:
        if inject_blocked(session) or not tmux_has(session):
            continue
        pane = f"{session}:0.0"
        cap = capture_pane(pane, lines=15)
        if not cap.get("ok"):
            continue
        prompt = _prompt_from_text(str(cap.get("text") or ""), pane)
        if prompt:
            found.append(prompt)
    return found
