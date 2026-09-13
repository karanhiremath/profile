#!/usr/bin/env python3
"""Isolation seats for Hermes/herm-tui aliases.

Each fleet alias owns exactly one isolated HERMES_HOME, one tmux session,
and at most one live TUI. A second TUI on the same home closes the gateway
pipe and leaves synthesizing hung. ~/.hermes is never a Cos/PM/notes seat.

Usage:
    alias_seat.py resolve <alias>
    alias_seat.py family <alias-or-profile>
    alias_seat.py lock-pid <profile>
    alias_seat.py attach-target <profile> [session]
    alias_seat.py write-seat <profile> <alias>
    alias_seat.py pin-env <alias>
    alias_seat.py homes <profile>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SEAT_FILENAME = "alias.seat.json"
LOCK_FILENAME = ".herm-tui.lock"

# Owned launcher names. Hermes-agent must not emit `hermes -p` wrappers
# that clobber these, and must not create same-named profiles under ~/.hermes.
OWNED_ALIASES = frozenset({
    "agents",
    "cos",
    "cos-m",
    "cosw",
    "cosw-m",
    "herm-tui-m",
    "notes",
    "notes-m",
    "notesw",
    "notesw-m",
    "pl",
    "pl-m",
    "pm",
    "pm-m",
})

OWNED_PROFILES = frozenset({
    "chief-of-staff",
    "chief-of-staff-work",
    "personal-notes-steward",
    "work-notes-steward",
    "notes-steward-work",
})

_SEATS: Tuple[Dict[str, Any], ...] = (
    {
        "family": "cos",
        "aliases": ("cos", "cos-m"),
        "profile": "chief-of-staff",
        "session": "cos",
        "desktop_window": "0",
        "mobile_window": "m",
        "lane": "personal",
    },
    {
        "family": "cosw",
        "aliases": ("cosw", "cosw-m"),
        "profile": "chief-of-staff-work",
        "session": "cosw",
        "desktop_window": "0",
        "mobile_window": "m",
        "lane": "work",
    },
    {
        "family": "notes",
        "aliases": ("notes", "notes-m"),
        "profile": "personal-notes-steward",
        "session": "notes",
        "desktop_window": "0",
        "mobile_window": "m",
        "lane": "personal",
    },
    {
        "family": "notesw",
        "aliases": ("notesw", "notesw-m"),
        "profile": "work-notes-steward",
        "alt_profiles": ("notes-steward-work",),
        "session": "notesw",
        "desktop_window": "0",
        "mobile_window": "m",
        "lane": "work",
    },
)


def data_home() -> Path:
    if override := os.environ.get("HERMES_AGENTS_DATA_HOME"):
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hermes-agents"


def fallback_hermes_home() -> Path:
    return Path.home() / ".hermes"


def isolated_root(profile: str) -> Path:
    return data_home() / profile


def runtime_home(profile: str, root: Optional[Path] = None) -> Path:
    home = root or isolated_root(profile)
    nested = home / "profiles" / profile
    if nested.is_dir():
        return nested
    return home


def lock_paths(profile: str) -> List[Path]:
    root = isolated_root(profile)
    runtime = runtime_home(profile, root)
    paths = [runtime / LOCK_FILENAME]
    if root != runtime:
        paths.append(root / LOCK_FILENAME)
    return paths


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_lock_pid(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        pid = int(raw.splitlines()[0].strip())
    except ValueError:
        return None
    return pid if _pid_alive(pid) else None


def lock_pid(profile: str) -> Optional[int]:
    for path in lock_paths(profile):
        pid = read_lock_pid(path)
        if pid is not None:
            return pid
    return None


def write_lock(profile: str, pid: int) -> Path:
    path = runtime_home(profile) / LOCK_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")
    return path


def clear_stale_locks(profile: str) -> List[str]:
    cleared: List[str] = []
    for path in lock_paths(profile):
        if not path.exists():
            continue
        if read_lock_pid(path) is None:
            try:
                path.unlink()
                cleared.append(str(path))
            except OSError:
                pass
    return cleared


def seat_by_alias(alias: str) -> Optional[Dict[str, Any]]:
    name = (alias or "").strip().lower()
    for seat in _SEATS:
        if name == seat["family"] or name in seat["aliases"]:
            return dict(seat)
    return None


def seat_by_profile(profile: str) -> Optional[Dict[str, Any]]:
    name = (profile or "").strip()
    for seat in _SEATS:
        names = (seat["profile"],) + tuple(seat.get("alt_profiles") or ())
        if name in names:
            found = dict(seat)
            found["profile"] = name
            return found
    return None


def resolve_alias(alias: str) -> Dict[str, Any]:
    seat = seat_by_alias(alias)
    if seat is None:
        raise SystemExit(f"ERROR: unknown isolation alias: {alias}")
    profile = str(seat["profile"])
    root = isolated_root(profile)
    runtime = runtime_home(profile, root)
    mobile = alias.endswith("-m") or alias.endswith("_m")
    window = seat["mobile_window"] if mobile else seat["desktop_window"]
    held = lock_pid(profile)
    return {
        "alias": alias,
        "family": seat["family"],
        "profile": profile,
        "session": seat["session"],
        "window": window,
        "desktop_window": seat["desktop_window"],
        "mobile_window": seat["mobile_window"],
        "lane": seat["lane"],
        "root": str(root),
        "runtime_home": str(runtime),
        "fallback_home": str(fallback_hermes_home()),
        "lock_held": held is not None,
        "lock_pid": held,
        "target": f"{seat['session']}:{window}",
        "pinned": True,
        "shares_fallback": False,
    }


def pin_env(alias: str) -> Dict[str, str]:
    info = resolve_alias(alias)
    return {
        "HERMES_HOME": info["runtime_home"],
        "HERMES_PROFILE": info["profile"],
        "HERMES_ALIAS": info["alias"],
        "HERMES_ALIAS_FAMILY": info["family"],
        "HERMES_ALIAS_PIN": "1",
        "HERMES_ALIAS_SESSION": info["session"],
    }


def seat_payload(profile: str, alias: str) -> Dict[str, Any]:
    info = resolve_alias(alias)
    if info["profile"] != profile and profile not in OWNED_PROFILES:
        raise SystemExit(f"ERROR: alias {alias} does not own profile {profile}")
    if info["profile"] != profile:
        info = resolve_alias(alias)
        info["profile"] = profile
        info["root"] = str(isolated_root(profile))
        info["runtime_home"] = str(runtime_home(profile))
    return {
        "family": info["family"],
        "aliases": list(seat_by_alias(alias)["aliases"]) if seat_by_alias(alias) else [alias],
        "profile": profile,
        "session": info["session"],
        "pinned": True,
        "runtime_home": info["runtime_home"],
        "root": info["root"],
    }


def write_seat(profile: str, alias: str) -> Path:
    root = isolated_root(profile)
    root.mkdir(parents=True, exist_ok=True)
    path = root / SEAT_FILENAME
    payload = seat_payload(profile, alias)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    runtime = runtime_home(profile, root)
    if runtime != root:
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / SEAT_FILENAME).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def read_seat(home: Path) -> Optional[Dict[str, Any]]:
    for cand in (home / SEAT_FILENAME, home.parent.parent / SEAT_FILENAME if home.parent.name == "profiles" else home / SEAT_FILENAME):
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("pinned"):
            return data
    return None


def pin_active() -> bool:
    return os.environ.get("HERMES_ALIAS_PIN", "").strip() in {"1", "true", "yes"}


def assert_not_fallback_home(home: Path) -> None:
    fallback = fallback_hermes_home().resolve()
    try:
        resolved = home.resolve()
    except OSError:
        resolved = home
    if resolved == fallback or fallback in resolved.parents:
        raise SystemExit(
            f"ERROR: alias seats cannot use {fallback}. "
            "Isolated homes live under hermes-agents/<profile>."
        )


def inbox_homes(profile: str) -> List[Path]:
    """Steering inboxes: isolated Cos/notes homes only. Never ~/.hermes."""
    root = isolated_root(profile)
    runtime = runtime_home(profile, root)
    homes = [root]
    if runtime != root:
        homes.append(runtime)
    return homes


def _ps_children() -> Dict[int, List[int]]:
    tree: Dict[int, List[int]] = {}
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return tree
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        tree.setdefault(ppid, []).append(pid)
    return tree


def pid_in_tree(root_pid: int, wanted: int) -> bool:
    if root_pid == wanted:
        return True
    tree = _ps_children()
    stack = [root_pid]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if cur == wanted:
            return True
        stack.extend(tree.get(cur, []))
    return False


def _tmux(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=False)


def list_tmux_panes() -> List[Dict[str, str]]:
    proc = _tmux(
        "list-panes",
        "-a",
        "-F",
        "#{session_name}\t#{window_name}\t#{pane_index}\t#{pane_pid}\t#{pane_current_command}\t#{session_name}:#{window_name}.#{pane_index}",
    )
    if proc.returncode != 0:
        return []
    rows: List[Dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        rows.append({
            "session": parts[0],
            "window": parts[1],
            "index": parts[2],
            "pid": parts[3],
            "command": parts[4],
            "target": parts[5],
        })
    return rows


def is_tui_command(command: str) -> bool:
    name = Path(command or "").name.lower()
    return name in {"herm", "hermes", "bun", "node"}


def attach_target(profile: str, session: Optional[str] = None) -> Optional[str]:
    """Return the tmux target that already holds this home's TUI."""
    held = lock_pid(profile)
    panes = list_tmux_panes()
    preferred = session or (seat_by_profile(profile) or {}).get("session")

    if held is not None:
        matches = []
        for pane in panes:
            try:
                pane_pid = int(pane["pid"])
            except ValueError:
                continue
            if pid_in_tree(pane_pid, held) or pane_pid == held:
                matches.append(pane)
        if preferred:
            for pane in matches:
                if pane["session"] == preferred:
                    return pane["target"]
        if matches:
            return matches[0]["target"]

    if preferred:
        for pane in panes:
            if pane["session"] == preferred and is_tui_command(pane["command"]):
                return pane["target"]
    return None


def homes_conflict(profile: str) -> List[str]:
    """Detect another alias family sharing this isolated home."""
    root = isolated_root(profile)
    seat = read_seat(root)
    expected = seat_by_profile(profile)
    if not seat or not expected:
        return []
    if seat.get("family") and seat.get("family") != expected.get("family"):
        return [
            f"home {root} is pinned to family {seat.get('family')} "
            f"but profile {profile} belongs to {expected.get('family')}"
        ]
    return []


def emit(data: Any) -> int:
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def main(argv: List[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    cmd, *rest = argv
    if cmd == "resolve":
        if not rest:
            raise SystemExit("ERROR: resolve needs an alias")
        return emit(resolve_alias(rest[0]))
    if cmd == "family":
        if not rest:
            raise SystemExit("ERROR: family needs an alias or profile")
        seat = seat_by_alias(rest[0]) or seat_by_profile(rest[0])
        if seat is None:
            raise SystemExit(f"ERROR: unknown seat: {rest[0]}")
        return emit(seat)
    if cmd == "lock-pid":
        if not rest:
            raise SystemExit("ERROR: lock-pid needs a profile")
        pid = lock_pid(rest[0])
        print("" if pid is None else str(pid))
        return 0 if pid is not None else 1
    if cmd == "attach-target":
        if not rest:
            raise SystemExit("ERROR: attach-target needs a profile")
        session = rest[1] if len(rest) > 1 else None
        target = attach_target(rest[0], session)
        if not target:
            return 1
        print(target)
        return 0
    if cmd == "write-seat":
        if len(rest) < 2:
            raise SystemExit("ERROR: write-seat needs <profile> <alias>")
        print(write_seat(rest[0], rest[1]))
        return 0
    if cmd == "pin-env":
        if not rest:
            raise SystemExit("ERROR: pin-env needs an alias")
        for key, value in pin_env(rest[0]).items():
            print(f"{key}={value}")
        return 0
    if cmd == "homes":
        if not rest:
            raise SystemExit("ERROR: homes needs a profile")
        for home in inbox_homes(rest[0]):
            print(home)
        return 0
    raise SystemExit(f"ERROR: unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
