#!/usr/bin/env python3
"""Isolation seats for Hermes/herm-tui aliases.

Each fleet alias owns exactly one isolated HERMES_HOME, one tmux session,
and at most one live TUI. A second TUI on the same home closes the gateway
pipe and leaves synthesizing hung. ~/.hermes is never a Cos/PM/notes seat.

`cos --lane NAME` / `cosw --lane NAME` mint a sibling seat
(`chief-of-staff-NAME`, tmux `cos-NAME`) so parallel TUIs do not share a home.

Usage:
    alias_seat.py resolve <alias>
    alias_seat.py resolve-profile <profile>
    alias_seat.py lane-profile <alias-or-profile> <lane>
    alias_seat.py family <alias-or-profile>
    alias_seat.py lock-pid <profile>
    alias_seat.py attach-target <profile> [session]
    alias_seat.py write-seat <profile> <alias>
    alias_seat.py pin-env <alias-or-profile>
    alias_seat.py homes <profile>
    alias_seat.py next-seat <alias-or-profile> [owner-pid]
    alias_seat.py claim <profile> <owner-pid> [transfer-token]
    alias_seat.py activate-claim <profile> <owner-pid> <token> <runtime-home>
    alias_seat.py release-claim <profile> <owner-pid> <token>
    alias_seat.py wait-transfer <profile> <owner-pid> <token>
    alias_seat.py run-claim <profile> <owner-pid> <token> <runtime-home> <command...>
    alias_seat.py sessions <alias-or-profile>

Spawn-always contract (enforced by agents/cosw launchers):
launchers NEVER attach to or switch a client toward an existing TUI. A busy
seat mints the next free sibling seat (`a1`, `a2`, ...) with its own
HERMES_HOME and tmux session via `next-seat`. Attaching is explicit only
(`agents attach` / `cosw attach`) and listing is `agents sessions`.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import secrets
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_INSTANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")

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
    # Match hermes_agents._data_home and the fork-env shim, including shared hosts.
    for key in ("AGENT_SHARED_HOME", "HERMES_SHARED_PEOPLE_HOME"):
        raw = (os.environ.get(key) or "").strip()
        if raw and Path(raw).expanduser().is_dir():
            return Path(raw).expanduser() / "hermes-agents"
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    shared = Path("/shared/people") / user
    if user and shared.is_dir():
        return shared / "hermes-agents"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hermes-agents"


def fallback_hermes_home() -> Path:
    return Path.home() / ".hermes"


def isolated_root(profile: str) -> Path:
    return data_home() / profile


def runtime_home(profile: str, root: Optional[Path] = None) -> Path:
    home = root or isolated_root(profile)
    try:
        active = (home / "active_profile").read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        active = profile
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", active) or active == "default":
        active = profile
    nested = home / "profiles" / active
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
    claim = _read_claim(profile)
    if claim and _pid_alive(claim["pid"]):
        return claim["pid"]
    for path in lock_paths(profile):
        pid = read_lock_pid(path)
        if pid is not None:
            return pid
    return None


def _claim_path(profile: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", profile):
        raise SystemExit(f"ERROR: invalid seat profile: {profile}")
    return data_home() / ".seat-claims" / f"{profile}.json"


@contextmanager
def _claim_guard(profile: str):
    # Never unlink this mutex: all generations must lock the same inode.
    path = _claim_path(profile).with_suffix(".guard")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        yield


def _read_claim(profile: str) -> Optional[Dict[str, Any]]:
    try:
        claim = json.loads(_claim_path(profile).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if (not isinstance(claim, dict) or not isinstance(claim.get("pid"), int)
            or not isinstance(claim.get("token"), str)):
        raise SystemExit(f"ERROR: malformed owner claim for {profile}")
    return claim


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + f".{os.getpid()}.{secrets.token_hex(8)}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _save_claim(profile: str, claim: Dict[str, Any]) -> None:
    _atomic_text(_claim_path(profile), json.dumps(claim) + "\n")


def claim_seat(profile: str, pid: int, token: str = "") -> Optional[str]:
    """Reserve before cloning/materialization; a token transfers a reservation only.

    The unguessable capability is passed explicitly in the tmux command, not
    adopted from a PID/ancestry guess or tmux's server-global environment.
    """
    if not _pid_alive(pid):
        raise SystemExit("ERROR: claim needs a live owner PID")
    with _claim_guard(profile):
        previous = _read_claim(profile)
        if token:
            if (not previous or previous["token"] != token
                    or previous.get("phase") != "reserved"):
                raise SystemExit(f"ERROR: invalid claim transfer for {profile}")
            # A reservation has no published PID lock; do not adopt a foreign TUI.
            if any(read_lock_pid(path) is not None for path in lock_paths(profile)):
                raise SystemExit(f"ERROR: live TUI blocks claim transfer for {profile}")
        else:
            if previous and _pid_alive(previous["pid"]):
                return None
            if any(read_lock_pid(path) is not None for path in lock_paths(profile)):
                return None
            token = secrets.token_hex(32)
        _save_claim(profile, {"pid": pid, "token": token, "phase": "reserved"})
        return token


def activate_claim(profile: str, pid: int, token: str, home: Path) -> None:
    with _claim_guard(profile):
        claim = _read_claim(profile)
        if not claim or (claim["pid"], claim["token"]) != (pid, token):
            raise SystemExit(f"ERROR: owner claim lost for {profile}")
        root = isolated_root(profile).resolve()
        if home.resolve() != root and root not in home.resolve().parents:
            raise SystemExit(f"ERROR: runtime home is outside claimed seat: {home}")
        if any(read_lock_pid(path) not in (None, pid) for path in lock_paths(profile)):
            raise SystemExit(f"ERROR: live TUI blocks launch for {profile}")
        path = home / LOCK_FILENAME
        # Record cleanup authority before publishing the compatibility lock.
        claim.update(phase="active", lock=str(path))
        _save_claim(profile, claim)
        _atomic_text(path, f"{pid}\n")


def release_claim(profile: str, pid: int, token: str) -> None:
    with _claim_guard(profile):
        claim = _read_claim(profile)
        if not claim or (claim["pid"], claim["token"]) != (pid, token):
            return
        if claim.get("lock"):
            path = Path(claim["lock"])
            try:
                owned_pids = (pid, claim.get("previous_pid", pid))
                if path.read_text(encoding="utf-8") in tuple(f"{owner}\n" for owner in owned_pids):
                    path.unlink()
            except FileNotFoundError:
                pass
        _claim_path(profile).unlink()


def run_claim(profile: str, pid: int, token: str, home: Path, argv: List[str]) -> int:
    """Exec the TUI with its own PID lock; supervise owner-checked exit cleanup.

    The child waits on a pipe until ownership and the plain compatibility PID
    lock are published. Unlike shell `exec`, the waiter survives failed execs
    and nonzero TUI exits without leaving its claim behind.
    """
    if not argv:
        raise SystemExit("ERROR: run-claim needs a command")
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(write_fd)
        ready = os.read(read_fd, 1)
        os.close(read_fd)
        if ready != b"1":
            os._exit(126)
        try:
            os.execvpe(argv[0], argv, os.environ)
        except OSError as error:
            print(f"ERROR: cannot launch {argv[0]}: {error}", file=sys.stderr, flush=True)
            os._exit(127)
    os.close(read_fd)
    handlers = {}

    def forward(signum, _frame):
        try:
            os.kill(child, signum)
        except ProcessLookupError:
            pass

    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, forward)
        with _claim_guard(profile):
            claim = _read_claim(profile)
            if (not claim or (claim["pid"], claim["token"]) != (pid, token)
                    or claim.get("phase") != "active"
                    or Path(claim["lock"]).resolve() != (home / LOCK_FILENAME).resolve()):
                raise SystemExit(f"ERROR: owner claim lost before exec for {profile}")
            path = home / LOCK_FILENAME
            if path.read_text(encoding="utf-8") != f"{pid}\n":
                raise SystemExit(f"ERROR: PID lock changed before exec for {profile}")
            # If publishing the child's PID fails, cleanup still recognizes
            # the compatibility lock belonging to this generation's launcher.
            claim.update(pid=child, previous_pid=pid)
            _save_claim(profile, claim)
            _atomic_text(path, f"{child}\n")
        os.write(write_fd, b"1")
        os.close(write_fd)
        write_fd = -1
        _, status = os.waitpid(child, 0)
        child_status = os.waitstatus_to_exitcode(status)
        return child_status if child_status >= 0 else 128 - child_status
    finally:
        if write_fd != -1:
            os.close(write_fd)
            # Failed preparation: the gated child exits without running argv.
            os.waitpid(child, 0)
        release_claim(profile, child, token)
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def wait_transfer(profile: str, pid: int, token: str) -> bool:
    """Keep the parent reservation alive until a detached tmux child adopts it."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        claim = _read_claim(profile)
        # A short-lived child can already have finished and cleaned up.
        if claim is None:
            return True
        if claim["token"] != token:
            return False
        if claim["pid"] != pid:
            return _pid_alive(claim["pid"])
        time.sleep(0.025)
    return False


def write_lock(profile: str, pid: int) -> Path:
    with _claim_guard(profile):
        held = lock_pid(profile)
        if held not in (None, pid):
            raise SystemExit(f"ERROR: seat {profile} already owned by {held}")
        path = runtime_home(profile) / LOCK_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_text(path, f"{pid}\n")
        return path


def clear_stale_locks(profile: str) -> List[str]:
    cleared: List[str] = []
    with _claim_guard(profile):
        claim = _read_claim(profile)
        if claim and _pid_alive(claim["pid"]):
            return cleared
        for path in lock_paths(profile):
            try:
                before = path.stat(), path.read_bytes()
                if read_lock_pid(path) is None and before == (path.stat(), path.read_bytes()):
                    path.unlink()
                    cleared.append(str(path))
            except FileNotFoundError:
                pass
        if claim:
            _claim_path(profile).unlink()
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


def parse_instance_profile(profile: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """Split chief-of-staff-o1 / chief-of-staff-work-o1 into (base seat, instance)."""
    name = (profile or "").strip()
    if not name:
        return None
    seats = sorted(_SEATS, key=lambda s: len(str(s["profile"])), reverse=True)
    for seat in seats:
        candidates = (seat["profile"],) + tuple(seat.get("alt_profiles") or ())
        for base in candidates:
            prefix = f"{base}-"
            if name.startswith(prefix):
                instance = name[len(prefix):]
                if instance:
                    found = dict(seat)
                    found["profile"] = base
                    return found, instance
    return None


def validate_instance(base_profile: str, instance: str) -> str:
    instance = (instance or "").strip()
    if not _INSTANCE_RE.fullmatch(instance):
        raise SystemExit(
            "ERROR: --lane needs a name like o1 or research "
            f"(got {instance!r})"
        )
    profile = f"{base_profile}-{instance}"
    owned = seat_by_profile(profile)
    if owned is not None:
        raise SystemExit(
            f"ERROR: --lane {instance} collides with {owned['family']} "
            f"profile {profile}"
        )
    return profile


def instance_profile(base: str, instance: str) -> str:
    seat = seat_by_profile(base) or seat_by_alias(base)
    if seat is None:
        parsed = parse_instance_profile(base)
        if parsed is None:
            raise SystemExit(f"ERROR: unknown lane family: {base}")
        validate_instance(str(parsed[0]["profile"]), parsed[1])
        return validate_instance(base, instance)
    return validate_instance(str(seat["profile"]), instance)


def seat_for_profile(profile: str) -> Optional[Dict[str, Any]]:
    name = (profile or "").strip()
    exact = seat_by_profile(name)
    if exact is not None:
        out = dict(exact)
        out["instance"] = ""
        return out
    parsed = parse_instance_profile(name)
    if parsed is None:
        return None
    base, instance = parsed
    validate_instance(str(base["profile"]), instance)
    out = dict(base)
    out["profile"] = f"{base['profile']}-{instance}"
    out["session"] = f"{base['session']}-{instance}"
    out["instance"] = instance
    return out


def _resolve_seat(seat: Dict[str, Any], alias: str = "") -> Dict[str, Any]:
    profile = str(seat["profile"])
    root = isolated_root(profile)
    runtime = runtime_home(profile, root)
    held = lock_pid(profile)
    aliases = tuple(seat.get("aliases") or ())
    mobile = bool(alias) and (alias.endswith("-m") or alias.endswith("_m"))
    window = seat["mobile_window"] if mobile else seat["desktop_window"]
    return {
        "alias": alias or (aliases[0] if aliases else seat["family"]),
        "family": seat["family"],
        "profile": profile,
        "session": seat["session"],
        "window": window,
        "desktop_window": seat["desktop_window"],
        "mobile_window": seat["mobile_window"],
        "lane": seat["lane"],
        "instance": seat.get("instance") or "",
        "root": str(root),
        "runtime_home": str(runtime),
        "fallback_home": str(fallback_hermes_home()),
        "lock_held": held is not None,
        "lock_pid": held,
        "target": f"{seat['session']}:{window}",
        "pinned": True,
        "shares_fallback": False,
    }


def resolve_profile(profile: str) -> Dict[str, Any]:
    seat = seat_for_profile(profile)
    if seat is None:
        raise SystemExit(f"ERROR: unknown isolation profile: {profile}")
    return _resolve_seat(seat)


def resolve_alias(alias: str) -> Dict[str, Any]:
    seat = seat_by_alias(alias)
    if seat is None:
        raise SystemExit(f"ERROR: unknown isolation alias: {alias}")
    seat = dict(seat)
    seat["instance"] = ""
    return _resolve_seat(seat, alias)


def pin_env(target: str) -> Dict[str, str]:
    if seat_by_alias(target):
        info = resolve_alias(target)
    else:
        info = resolve_profile(target)
    env = {
        "HERMES_HOME": info["runtime_home"],
        "HERMES_PROFILE": info["profile"],
        "HERMES_ALIAS": info["alias"],
        "HERMES_ALIAS_FAMILY": info["family"],
        "HERMES_ALIAS_PIN": "1",
        "HERMES_ALIAS_SESSION": info["session"],
    }
    if info.get("instance"):
        env["HERMES_LANE"] = str(info["instance"])
    return env


def seat_payload(profile: str, alias: str) -> Dict[str, Any]:
    mapped = seat_for_profile(profile)
    if mapped is not None and mapped.get("instance"):
        family_alias = seat_by_alias(alias)
        if family_alias is not None and family_alias["family"] != mapped["family"]:
            raise SystemExit(
                f"ERROR: alias {alias} does not own profile {profile}"
            )
        return {
            "family": mapped["family"],
            "aliases": list(mapped["aliases"]),
            "profile": profile,
            "session": mapped["session"],
            "lane": mapped["lane"],
            "instance": mapped["instance"],
            "pinned": True,
            "runtime_home": str(runtime_home(profile)),
            "root": str(isolated_root(profile)),
        }
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
    # Prefer the stable pane id (%N) as the attach target: window names are
    # volatile under automatic-rename (a node pane exiting renames the window
    # between listing and attach -> 'can't find window: <name>'), and demo
    # sessions routinely carry duplicate window names.
    proc = _tmux(
        "list-panes",
        "-a",
        "-F",
        "#{session_name}\t#{window_name}\t#{pane_index}\t#{pane_pid}\t#{pane_current_command}\t#{session_name}:#{window_name}.#{pane_index}\t#{pane_id}",
    )
    if proc.returncode != 0:
        return []
    rows: List[Dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        pane_id = parts[6].strip()
        rows.append({
            "session": parts[0],
            "window": parts[1],
            "index": parts[2],
            "pid": parts[3],
            "command": parts[4],
            "target": pane_id if pane_id else parts[5],
            "name_target": parts[5],
        })
    return rows


def is_tui_command(command: str) -> bool:
    name = Path(command or "").name.lower()
    return name in {"herm", "hermes", "bun", "node"}


def attach_target(profile: str, session: Optional[str] = None) -> Optional[str]:
    """Return the tmux target that already holds this home's TUI."""
    held = lock_pid(profile)
    panes = list_tmux_panes()
    preferred = session or (seat_for_profile(profile) or {}).get("session")

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


def _base_seat(key: str) -> Optional[Dict[str, Any]]:
    seat = seat_by_alias(key) or seat_by_profile(key)
    if seat is None:
        parsed = parse_instance_profile(key)
        seat = parsed[0] if parsed else None
    return seat


def family_sessions(key: str) -> Dict[str, Any]:
    """List tmux sessions for a seat family (base session + <base>-* lanes)."""
    seat = _base_seat(key)
    if seat is None:
        raise SystemExit(f"ERROR: unknown seat: {key}")
    base_session = str(seat["session"])
    rows: List[Dict[str, Any]] = []
    proc = _tmux(
        "list-sessions",
        "-F",
        "#{session_name}\t#{session_attached}\t#{session_created_string}",
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            name = parts[0].strip()
            if name != base_session and not name.startswith(f"{base_session}-"):
                continue
            instance = (
                name[len(base_session) + 1:]
                if name.startswith(f"{base_session}-")
                else ""
            )
            profile = str(seat["profile"]) + (f"-{instance}" if instance else "")
            rows.append({
                "session": name,
                "profile": profile,
                "instance": instance,
                "attached": len(parts) > 1 and parts[1] == "1",
                "created": parts[2] if len(parts) > 2 else "",
                "lock_pid": lock_pid(profile),
            })
    return {
        "family": seat["family"],
        "base_session": base_session,
        "sessions": rows,
    }


def next_seat(key: str, owner_pid: Optional[int] = None) -> Dict[str, Any]:
    """Select a sibling; launchers supply a PID to reserve it atomically.

    Without a PID this is a read-only preview (for --dry-run).
    """
    seat = _base_seat(key)
    if seat is None:
        raise SystemExit(f"ERROR: unknown seat: {key}")
    base_profile = str(seat["profile"])
    base_session = str(seat["session"])
    # Sibling-of-lane: next-seat on an instance profile nests under that lane
    # (chief-of-staff-work-o1 -> chief-of-staff-work-o1-a1, tmux cosw-o1-a1).
    key_stripped = key.strip()
    parsed = parse_instance_profile(key_stripped)
    if parsed is not None and key_stripped != base_profile:
        base_profile = key_stripped
        base_session = f"{base_session}-{parsed[1]}"
    have_tmux = shutil.which("tmux") is not None
    for i in range(1, 100):
        instance = f"a{i}"
        profile = validate_instance(base_profile, instance)
        session = f"{base_session}-{instance}"
        if lock_pid(profile) is not None:
            continue
        if have_tmux and _tmux("has-session", "-t", session).returncode == 0:
            continue
        token = claim_seat(profile, owner_pid) if owner_pid is not None else ""
        if owner_pid is not None and token is None:
            continue
        root = isolated_root(profile)
        return {
            "claim_token": token,
            "family": seat["family"],
            "lane": seat["lane"],
            "instance": instance,
            "profile": profile,
            "session": session,
            "root": str(root),
            "runtime_home": str(runtime_home(profile, root)),
        }
    raise SystemExit("ERROR: no free sibling seat (a1..a99 exhausted)")


def homes_conflict(profile: str) -> List[str]:
    """Detect another alias family sharing this isolated home."""
    root = isolated_root(profile)
    seat = read_seat(root)
    expected = seat_for_profile(profile)
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
    if cmd == "resolve-profile":
        if not rest:
            raise SystemExit("ERROR: resolve-profile needs a profile")
        return emit(resolve_profile(rest[0]))
    if cmd == "lane-profile":
        if len(rest) < 2:
            raise SystemExit("ERROR: lane-profile needs <alias-or-profile> <lane>")
        print(instance_profile(rest[0], rest[1]))
        return 0
    if cmd == "family":
        if not rest:
            raise SystemExit("ERROR: family needs an alias or profile")
        seat = seat_by_alias(rest[0]) or seat_for_profile(rest[0])
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
    if cmd == "claim":
        if len(rest) < 2:
            raise SystemExit("ERROR: claim needs <profile> <pid> [transfer-token]")
        token = claim_seat(rest[0], int(rest[1]), rest[2] if len(rest) > 2 else "")
        if token is None:
            return 1
        print(token)
        return 0
    if cmd == "run-claim":
        if len(rest) < 5:
            raise SystemExit("ERROR: run-claim needs <profile> <pid> <token> <home> <command...>")
        return run_claim(rest[0], int(rest[1]), rest[2], Path(rest[3]), rest[4:])
    if cmd == "wait-transfer":
        if len(rest) != 3:
            raise SystemExit("ERROR: wait-transfer needs <profile> <pid> <token>")
        if not wait_transfer(rest[0], int(rest[1]), rest[2]):
            raise SystemExit(f"ERROR: tmux child did not adopt seat {rest[0]}")
        return 0
    if cmd == "activate-claim":
        if len(rest) != 4:
            raise SystemExit("ERROR: activate-claim needs <profile> <pid> <token> <home>")
        activate_claim(rest[0], int(rest[1]), rest[2], Path(rest[3]))
        return 0
    if cmd == "release-claim":
        if len(rest) != 3:
            raise SystemExit("ERROR: release-claim needs <profile> <pid> <token>")
        release_claim(rest[0], int(rest[1]), rest[2])
        return 0
    if cmd == "next-seat":
        if not rest:
            raise SystemExit("ERROR: next-seat needs an alias or profile")
        return emit(next_seat(rest[0], int(rest[1]) if len(rest) > 1 else None))
    if cmd == "sessions":
        if not rest:
            raise SystemExit("ERROR: sessions needs an alias or profile")
        return emit(family_sessions(rest[0]))
    if cmd == "write-seat":
        if len(rest) < 2:
            raise SystemExit("ERROR: write-seat needs <profile> <alias>")
        print(write_seat(rest[0], rest[1]))
        return 0
    if cmd == "pin-env":
        if not rest:
            raise SystemExit("ERROR: pin-env needs an alias or profile")
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
