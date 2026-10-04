#!/usr/bin/env python3
"""cmdk catalog + layer hooks. Stdlib only.

Send-keys policy matches bin/ghostty-voice/lanes.py: never inject into Cos /
cos-* / Atop. Worker lanes and pc `pi_*` harness panes may receive a prompt
buffer. Cos / plan get inbox/atop, not tmux input-buffer.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROFILE_DIR = Path(os.environ.get("PROFILE_DIR") or Path(__file__).resolve().parents[2])
CATALOG_PATH = PROFILE_DIR / "config" / "shell" / "cmdk" / "catalog.json"
PROFILES_PATH = (
    PROFILE_DIR / "config" / "pi" / "packages" / "pi-profile-management" / "manifests" / "profiles.json"
)
VOICE_VIEW = "http://127.0.0.1:8787/view"

WORKER_SESSIONS = tuple(f"ao{i}" for i in range(5)) + tuple(f"infra{i}" for i in range(5))
BLOCKED_SESSIONS = {
    "cos",
    "atop",
    "this",
    "pi",
    "pm",
    "pl",
    "notes",
    "claude",
    "chief",
    "cosw",
    "chief-of-staff-work",
}
HARNESS_CMDS = {
    "pi",
    "claude",
    "codex",
    "cursor-agent",
    "agent",
    "hermes",
    "herm-tui",
    "omni",
    "omnigent",
}
OTEL_CMDS = {"btop", "k9s", "htop"}
OTEL_TITLE_HINTS = ("otel", "metrics", "datadog", "dd/", "grafana")
NVIM_CMDS = {"nvim", "vim", "vi"}
SHELL_CMDS = {"zsh", "bash", "fish", "sh"}

TMUX = shutil.which("tmux") or "/opt/homebrew/bin/tmux"


def _run(argv: list[str], timeout: float = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema") != "profile.cmdk.v1":
        raise ValueError(f"unsupported catalog schema: {data.get('schema')}")
    return data


def load_profile_classes(path: Path = PROFILES_PATH) -> list[str]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text())
    classes = sorted((data.get("classes") or {}).keys())
    agents = sorted((data.get("agents") or {}).keys())
    return classes + [f"agent:{name}" for name in agents]


def session_name(target: str) -> str:
    return (target or "").split(":")[0].strip()


def inject_blocked(target: str) -> bool:
    name = session_name(target)
    if not name:
        return True
    if name in BLOCKED_SESSIONS:
        return True
    if name.startswith("cos-") or name.startswith("atop"):
        return True
    return False


def send_keys_allowed(target: str, pane_cmd: str = "") -> bool:
    name = session_name(target)
    if not name:
        return False
    if name in WORKER_SESSIONS:
        return True
    if name.startswith("pi_") and (not pane_cmd or pane_cmd in HARNESS_CMDS):
        return True
    return False


def detect_layer(
    pane_cmd: str = "",
    title: str = "",
    session: str = "",
    window: str = "",
) -> str:
    cmd = (pane_cmd or "").split("/")[-1].strip()
    blob = f"{title} {window} {session}".lower()
    if cmd in NVIM_CMDS:
        return "nvim"
    if cmd in HARNESS_CMDS:
        return "harness"
    if cmd in OTEL_CMDS or any(hint in blob for hint in OTEL_TITLE_HINTS):
        return "otel"
    if session.startswith("cos") or session.startswith("atop"):
        return "harness"
    if cmd in SHELL_CMDS or not cmd:
        return "zsh"
    if os.environ.get("TERM_PROGRAM") == "ghostty" and not os.environ.get("TMUX"):
        return "ghostty"
    return "tmux"


def live_pane() -> dict[str, str]:
    if not shutil.which("tmux") and not Path(TMUX).exists():
        return {}
    fmt = "#{session_name}\t#{window_name}\t#{pane_current_command}\t#{pane_title}\t#{pane_id}\t#{pane_tty}"
    proc = _run([TMUX, "display-message", "-p", fmt])
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    session, window, cmd, title, pane_id, tty = (proc.stdout.rstrip("\n").split("\t") + [""] * 6)[:6]
    target = f"{session}:{window}.{pane_id}" if session else ""
    # pane_id is like %12; tmux -t %12 is the stable target
    return {
        "session": session,
        "window": window,
        "cmd": cmd,
        "title": title,
        "pane_id": pane_id,
        "tty": tty,
        "target": pane_id or target,
    }


def detect_live() -> dict[str, Any]:
    pane = live_pane()
    layer = detect_layer(
        pane_cmd=pane.get("cmd", ""),
        title=pane.get("title", ""),
        session=pane.get("session", ""),
        window=pane.get("window", ""),
    )
    if not pane and os.environ.get("TERM_PROGRAM") == "ghostty":
        layer = "ghostty"
    target = pane.get("target") or pane.get("session") or ""
    return {
        "ok": True,
        "layer": layer,
        "pane": pane,
        "inject_blocked": inject_blocked(pane.get("session") or ""),
        "send_keys_allowed": send_keys_allowed(target, pane.get("cmd", "")),
    }


def tmux_sessions() -> list[str]:
    proc = _run([TMUX, "list-sessions", "-F", "#{session_name}"])
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def list_actions() -> list[dict[str, Any]]:
    catalog = load_catalog()
    rows: list[dict[str, Any]] = []
    for action in catalog.get("actions") or []:
        rows.append(
            {
                "id": action["id"],
                "title": action.get("title") or action["id"],
                "layer": action.get("layer") or "zsh",
                "tags": ",".join(action.get("tags") or []),
                "kind": "catalog",
            }
        )
    for sess in tmux_sessions():
        blocked = "blocked" if inject_blocked(sess) else "switch"
        rows.append(
            {
                "id": f"session:{sess}",
                "title": f"tmux session {sess} ({blocked})",
                "layer": "tmux",
                "tags": f"session,{sess}",
                "kind": "session",
            }
        )
    for cls in load_profile_classes():
        if cls.startswith("agent:"):
            name = cls.split(":", 1)[1]
            rows.append(
                {
                    "id": f"agent:{name}",
                    "title": f"pi agent {name}",
                    "layer": "harness",
                    "tags": "pi,agent,profile",
                    "kind": "profile-agent",
                }
            )
        else:
            rows.append(
                {
                    "id": f"class:{cls}",
                    "title": f"pi profile class {cls}",
                    "layer": "harness",
                    "tags": "pi,class,profile",
                    "kind": "profile-class",
                }
            )
    for lane in list(WORKER_SESSIONS):
        rows.append(
            {
                "id": f"lane:{lane}",
                "title": f"fleet attach {lane}",
                "layer": "tmux",
                "tags": f"fleet,lane,{lane}",
                "kind": "lane",
            }
        )
    return rows


def _print_tsv(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print(f"{row['id']}\t{row['title']}\t{row['layer']}\t{row.get('tags', '')}")


def switch_session(session: str) -> dict[str, Any]:
    if inject_blocked(session) and not session.startswith("pi_"):
        # Switching the client to Cos is fine; injecting is not.
        pass
    proc = _run([TMUX, "switch-client", "-t", session])
    if proc.returncode != 0:
        proc = _run([TMUX, "attach", "-t", session])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    return {"ok": True, "session": session}


def inject(text: str, target: str = "", pane_cmd: str = "") -> dict[str, Any]:
    cleaned = (text or "").replace("\r", " ").strip()
    if not cleaned:
        return {"ok": False, "error": "empty text"}
    pane = live_pane() if not target else {}
    dest = target or pane.get("pane_id") or pane.get("session") or ""
    cmd = pane_cmd or pane.get("cmd", "")
    sess = session_name(dest) if ":" in dest or dest.startswith("%") else dest
    if dest.startswith("%"):
        sess = pane.get("session") or sess
    if inject_blocked(sess or dest) and not send_keys_allowed(sess or dest, cmd):
        return {
            "ok": False,
            "error": f"blocked target {sess or dest} (Cos/Atop/plan use inbox, not send-keys)",
        }
    if not send_keys_allowed(sess or dest, cmd):
        return {"ok": False, "error": f"send-keys not allowed for {sess or dest}"}
    typed = _run([TMUX, "send-keys", "-t", dest, "-l", "--", cleaned])
    if typed.returncode != 0:
        return {"ok": False, "error": (typed.stderr or typed.stdout).strip()}
    entered = _run([TMUX, "send-keys", "-t", dest, "Enter"])
    if entered.returncode != 0:
        return {"ok": False, "error": (entered.stderr or entered.stdout).strip()}
    return {"ok": True, "target": dest, "layer": "harness"}


def select_otel() -> dict[str, Any]:
    body = json.dumps({"view": "otel"}).encode()
    req = urllib.request.Request(
        VOICE_VIEW,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            payload = json.loads(resp.read().decode() or "{}")
            return {"ok": True, "via": "ghostty-voice", "result": payload}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        voice_err = str(err)
    proc = _run(
        [
            TMUX,
            "list-panes",
            "-a",
            "-F",
            "#{session_name}:#{window_name}.#{pane_id}\t#{pane_current_command}\t#{pane_title}",
        ]
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            target, cmd = parts[0], parts[1]
            title = parts[2] if len(parts) > 2 else ""
            if detect_layer(cmd, title, session_name(target), "") == "otel":
                switched = _run([TMUX, "switch-client", "-t", session_name(target)])
                _run([TMUX, "select-pane", "-t", target.split(".")[-1] if "." in target else target])
                return {
                    "ok": switched.returncode == 0,
                    "via": "tmux-pane",
                    "target": target,
                    "voice_error": voice_err,
                }
    return {"ok": False, "error": f"otel view unavailable ({voice_err})"}


def focus_pc_role(role: str) -> dict[str, Any]:
    pane = live_pane()
    session = pane.get("session") or ""
    if not session.startswith("pi_"):
        return {"ok": False, "error": f"not a pc session ({session or 'none'})"}
    index = {"nvim": "0", "pi": "1", "zsh": "2"}.get(role)
    if index is None:
        return {"ok": False, "error": f"unknown pc role {role}"}
    target = f"{session}:.{index}"
    proc = _run([TMUX, "select-pane", "-t", target])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    return {"ok": True, "target": target, "role": role}


def _resolve_run(argv: list[str]) -> list[str] | None:
    if not argv:
        return []
    if argv[0] == "reload":
        return None
    mapping = {
        "attach": PROFILE_DIR / "bin" / "tmux" / "interactive",
        "pc": Path.home() / ".local" / "bin" / "pc",
        "fleet": PROFILE_DIR / "bin" / "fleet" / "fleet",
        "pi-p": PROFILE_DIR / "bin" / "pi-perplexity" / "pi-perplexity",
        "cmdk": PROFILE_DIR / "bin" / "cmdk" / "cmdk",
    }
    resolved = mapping.get(argv[0])
    if resolved and resolved.exists():
        return [str(resolved), *argv[1:]]
    return argv


def run_action(action_id: str, text: str = "") -> dict[str, Any]:
    if action_id.startswith("session:"):
        return switch_session(action_id.split(":", 1)[1])
    if action_id.startswith("lane:"):
        lane = action_id.split(":", 1)[1]
        fleet = PROFILE_DIR / "bin" / "fleet" / "fleet"
        if fleet.is_file():
            proc = _run(["zsh", str(fleet), "attach", lane])
            return {"ok": proc.returncode == 0, "lane": lane, "error": (proc.stderr or "").strip()}
        return switch_session(lane)
    if action_id.startswith("class:"):
        return {"ok": True, "export": {"PI_PROFILE_CLASS": action_id.split(":", 1)[1]}}
    if action_id.startswith("agent:"):
        return {"ok": True, "export": {"PI_PROFILE_AGENT": action_id.split(":", 1)[1]}}
    catalog = load_catalog()
    for action in catalog.get("actions") or []:
        if action.get("id") != action_id:
            continue
        mode = action.get("mode") or "run"
        if mode == "prompt-buffer":
            return inject(text)
        if mode == "otel":
            return select_otel()
        argv = _resolve_run(list(action.get("run") or []))
        if argv is None:
            return {"ok": True, "note": "run `reload` in the parent zsh"}
        if not argv:
            return {"ok": False, "error": f"action {action_id} has no run"}
        if Path(argv[0]).name == "cmdk" or argv[0] == "cmdk":
            rest = argv[1:]
            if rest[:1] == ["inject"]:
                return inject(text)
            if rest[:1] == ["otel"]:
                return select_otel()
            if rest[:1] == ["focus"] and len(rest) > 1:
                return focus_pc_role(rest[1])
        return {"ok": True, "exec": argv}
    return {"ok": False, "error": f"unknown action {action_id}"}


def emit(payload: Any) -> int:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if (not isinstance(payload, dict) or payload.get("ok", True)) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cmdk-lib")
    sub = parser.add_subparsers(dest="verb", required=True)

    p_layer = sub.add_parser("layer")
    p_layer.add_argument("--pane-cmd", dest="pane_cmd", default="")
    p_layer.add_argument("--title", default="")
    p_layer.add_argument("--session", default="")
    p_layer.add_argument("--window", default="")
    p_layer.add_argument("--live", action="store_true")

    p_list = sub.add_parser("list")
    p_list.add_argument("--tsv", action="store_true")
    p_list.add_argument("--json", action="store_true")

    sub.add_parser("detect")
    sub.add_parser("classes")
    p_run = sub.add_parser("run")
    p_run.add_argument("id")
    p_run.add_argument("--text", default="")
    p_inj = sub.add_parser("inject")
    p_inj.add_argument("--target", default="")
    p_inj.add_argument("--text", default="")
    p_inj.add_argument("words", nargs="*")
    sub.add_parser("otel")
    p_focus = sub.add_parser("focus")
    p_focus.add_argument("role", choices=["nvim", "pi", "zsh"])
    p_block = sub.add_parser("blocked")
    p_block.add_argument("target")

    args = parser.parse_args(argv)
    if args.verb == "layer":
        if args.live:
            return emit(detect_live())
        layer = detect_layer(args.pane_cmd, args.title, args.session, args.window)
        return emit({"ok": True, "layer": layer})
    if args.verb == "list":
        rows = list_actions()
        if args.tsv:
            _print_tsv(rows)
            return 0
        return emit({"ok": True, "actions": rows})
    if args.verb == "detect":
        return emit(detect_live())
    if args.verb == "classes":
        return emit({"ok": True, "classes": load_profile_classes()})
    if args.verb == "run":
        return emit(run_action(args.id, args.text))
    if args.verb == "inject":
        text = args.text or " ".join(args.words)
        return emit(inject(text, args.target))
    if args.verb == "otel":
        return emit(select_otel())
    if args.verb == "focus":
        return emit(focus_pc_role(args.role))
    if args.verb == "blocked":
        return emit(
            {
                "ok": True,
                "target": args.target,
                "inject_blocked": inject_blocked(args.target),
                "send_keys_allowed": send_keys_allowed(args.target),
            }
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
