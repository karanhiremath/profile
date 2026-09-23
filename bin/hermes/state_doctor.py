#!/usr/bin/env python3
"""Hermes profile state-store doctor — census, preflight, and guarded repair.

Complements `hermes doctor` (upstream, interactive) and
`project_sessions.py doctor` (dispatch layer only — has zero state.db
awareness). This module owns the *state lane* contract:

  P1  SQLite state.db only where POSIX locks work (never WAL on NFS).
  P2  One writer per profile; writers are censused, never assumed.
  P3  AF_UNIX sockets bind under paths <= 108 bytes.
  P6  Fail fast on the NFS+WAL combination instead of corrupting.

Contract (Cartesia CLI pipeline): stdout is machine JSON only
(schema_version: hermes.state-doctor.v1); stderr is human diagnostics.
Exit codes: 0 ok, 1 failed check / refused repair, 2 usage.

Subcommands:
  census    [--profile NAME | --all]   read-only state report
  preflight --profile NAME             launch gate for cosw / agents up
  repair    --profile NAME [--yes] [--salvage]
                                       quarantine + fresh DELETE-journal store
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "hermes.state-doctor.v1"
SQLITE_MAGIC = b"SQLite format 3\x00"
TICK_SOCKET_TEMPLATE = "state/gateway.loop-tick.{pid}.sock"
AF_UNIX_SUN_PATH_MAX = 108


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ── paths ────────────────────────────────────────────────────────────────────

def agents_data_home() -> Path:
    raw = (
        os.environ.get("HERMES_AGENTS_DATA_HOME")
        or (f"{os.environ['AGENT_SHARED_HOME']}/hermes-agents"
            if os.environ.get("AGENT_SHARED_HOME") else None)
        or f"/shared/people/{os.environ.get('USER', os.environ.get('LOGNAME', ''))}/hermes-agents"
    )
    return Path(raw).expanduser()


def runtime_home(profile: str) -> Path:
    """Materialized runtime home: <root>/<profile>/profiles/<profile> (nested
    layout) falling back to <root>/<profile> (flat)."""
    root = agents_data_home()
    nested = root / profile / "profiles" / profile
    if nested.is_dir():
        return nested
    return root / profile


def db_paths(home: Path) -> dict[str, Path]:
    return {
        "db": home / "state.db",
        "wal": home / "state.db-wal",
        "shm": home / "state.db-shm",
    }


# ── probes ───────────────────────────────────────────────────────────────────

def read_db_header(path: Path, nbytes: int = 32) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read(nbytes)
    except OSError:
        return None


def header_is_sqlite(header: bytes | None) -> bool:
    return bool(header) and header[:16] == SQLITE_MAGIC


def header_journal_mode(header: bytes | None) -> str | None:
    """SQLite header bytes 18/19 are the file format write/read versions.
    1 = legacy (rollback journal), 2 = WAL."""
    if not header_is_sqlite(header) or len(header) < 20:
        return None
    write_ver, read_ver = header[18], header[19]
    if (write_ver, read_ver) == (2, 2):
        return "wal"
    if (write_ver, read_ver) == (1, 1):
        return "delete"
    return f"write={write_ver} read={read_ver}"


def classify_store(home: Path) -> dict[str, Any]:
    """Classify state.db without needing write locks: header first, PRAGMA
    second. status ∈ missing | malformed | locking-protocol | integrity-errors
    | busy | probe-error | ok."""
    db, wal = home / "state.db", home / "state.db-wal"
    if not db.exists():
        return {"status": "missing", "journal_mode": None, "size_bytes": 0,
                "detail": "no state.db (fresh profile)"}
    size = db.stat().st_size
    header = read_db_header(db)
    out: dict[str, Any] = {"status": "unknown", "journal_mode": None,
                           "size_bytes": size, "detail": ""}
    if not header_is_sqlite(header):
        return {"status": "malformed", "journal_mode": None, "size_bytes": size,
                "detail": "header is not SQLite magic (bytes 0-15)"}
    mode = header_journal_mode(header)
    out["journal_mode"] = mode
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            result = row[0] if row else "no-row"
            if result == "ok":
                out["status"] = "ok"
            else:
                out["status"] = "integrity-errors"
                out["detail"] = str(result)[:200]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        text = str(exc)
        if "locking protocol" in text:
            out["status"] = "locking-protocol"
            out["detail"] = "PRAGMA probe raised SQLITE_PROTOCOL (NFS/SMB lock semantics)"
        elif "malformed" in text or "not a database" in text:
            out["status"] = "malformed"
            out["detail"] = text[:200]
        elif "locked" in text:
            out["status"] = "busy"
            out["detail"] = text[:200]
        else:
            out["status"] = "probe-error"
            out["detail"] = text[:200]
    if home.joinpath("state.db-wal").exists() and mode == "delete":
        out["detail"] = (out["detail"] + " orphan -wal sidecar present").strip()
    return out


def fs_type_of(path: Path) -> str:
    try:
        out = subprocess.run(
            ["stat", "-f", "-c", "%T", str(path)],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip() or "unknown"
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def is_nfs(fs: str) -> bool:
    return fs.startswith("nfs")


def pid_cmdline(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except (OSError, ValueError):
        return None


def pid_environ(pid: int) -> dict[str, str]:
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            raw = fh.read().split(b"\0")
    except (OSError, ValueError):
        return {}
    env: dict[str, str] = {}
    for item in env_raw_items(raw):
        key, _, value = item.partition("=")
        env[key] = value
    return env


def env_raw_items(raw: list[bytes]) -> list[str]:
    return [item.decode("utf-8", "replace") for item in raw if b"=" in item]


def live_writer_pids(home: Path) -> list[dict[str, Any]]:
    """PIDs with HERMES_HOME == this profile home whose cmdline is a
    gateway / tui_gateway writer. /proc scan, same-user only. Paths are
    realpath-normalized: the fleet exports both /shared/... and the
    resolved /data_vast/... form of the same home."""
    target = os.path.realpath(home)
    writers: list[dict[str, Any]] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == os.getpid():
            continue
        env = pid_environ(pid)
        if not env.get("HERMES_HOME") or os.path.realpath(env["HERMES_HOME"]) != target:
            continue
        cmdline = pid_cmdline(pid) or ""
        role = None
        if "hermes_cli.main" in cmdline and "gateway" in cmdline:
            role = "gateway"
        elif "tui_gateway" in cmdline:
            role = "tui_gateway"
        if role:
            writers.append({"pid": pid, "role": role, "cmdline": cmdline[:160]})
    return writers


def flock_holder(home: Path) -> dict[str, Any]:
    holder = home / ".gateway.lock.holder"
    out: dict[str, Any] = {"file": str(holder), "present": holder.exists(),
                           "alive": False, "host": None, "pid": None, "started": None}
    if not holder.exists():
        return out
    fields: dict[str, str] = {}
    try:
        for line in holder.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip():
                fields[key.strip()] = value.strip()
    except OSError:
        out["error"] = "unreadable"
        return out
    out["host"] = fields.get("host")
    out["started"] = fields.get("started")
    try:
        out["pid"] = int(fields["pid"]) if fields.get("pid") else None
    except ValueError:
        out["pid"] = None
    pid = out["pid"]
    if pid is not None and pid_cmdline(pid) and "hermes" in (pid_cmdline(pid) or ""):
        out["alive"] = True
    return out


def tick_socket_probe(home: Path) -> dict[str, Any]:
    path = home / TICK_SOCKET_TEMPLATE.format(pid=os.getpid())
    length = len(str(path))
    return {"path": str(path), "length": length,
            "ok": length <= AF_UNIX_SUN_PATH_MAX, "limit": AF_UNIX_SUN_PATH_MAX}


def spool_pending(home: Path) -> int:
    spool = home / "host-control" / "legacy-spool"
    if not spool.is_dir():
        return 0
    try:
        return sum(1 for _ in spool.iterdir())
    except OSError:
        return -1


# ── census / preflight ───────────────────────────────────────────────────────

def census_profile(profile: str) -> dict[str, Any]:
    home = runtime_home(profile)
    store = classify_store(home)
    fs = fs_type_of(home)
    writers = live_writer_pids(home)
    holder = flock_holder(home)
    tick = tick_socket_probe(home)
    mode = store.get("journal_mode")
    checks: list[dict[str, str]] = []
    hard_fail = False

    def add(cid: str, status: str, detail: str, hard: bool = False) -> None:
        nonlocal hard_fail
        checks.append({"id": cid, "status": status, "detail": detail})
        if status == "fail" and hard:
            hard_fail = True

    if store["status"] == "missing":
        add("store.integrity", "warn", "no state.db yet (fresh profile lane)", False)
    elif store["status"] == "ok":
        add("store.integrity", "pass", "quick_check ok", False)
    else:
        add("store.integrity", "fail",
            f"store status={store['status']}: {store['detail']}", True)

    if mode == "wal" and is_nfs(fs):
        add("journal.nfs-wal", "fail",
            f"journal=wal on fs={fs} — NFS/NLM locks are not crash-atomic for "
            "WAL; convert offline to journal_mode=delete", True)
    elif mode in ("wal", "delete"):
        add("journal.nfs-wal", "pass", f"journal={mode} on fs={fs}", False)
    else:
        add("journal.nfs-wal", "warn", f"journal undetermined (fs={fs})", False)

    if len(writers) > 1:
        add("writers.single", "fail",
            f"{len(writers)} live writers: "
            + "; ".join(f"pid={w['pid']} role={w['role']}" for w in writers), True)
    elif len(writers) == 1:
        add("writers.single", "pass",
            f"one writer pid={writers[0]['pid']} role={writers[0]['role']}", False)
    else:
        add("writers.single", "warn", "no live gateway writer (ok pre-launch)", False)

    if tick["ok"]:
        add("afunix.path-length", "pass", f"tick path {tick['length']} chars", False)
    else:
        add("afunix.path-length", "fail",
            f"tick socket path is {tick['length']} chars > {tick['limit']}: {tick['path']}", True)

    if holder.get("present"):
        if holder.get("alive"):
            add("flock.holder", "pass",
                f"holder pid={holder['pid']} host={holder.get('host')}", False)
        else:
            add("flock.holder", "warn",
                f"stale holder metadata host={holder.get('host')} "
                f"pid={holder.get('pid')} started={holder.get('started')}", False)

    pending = spool_pending(home)
    if pending > 0:
        add("spool.drain", "warn", f"{pending} pending spool item(s)", False)

    hard = [c for c in checks if c["status"] == "fail"]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "profile": profile,
        "hermes_home": str(home),
        "fs": fs,
        "db": store,
        "writers": writers,
        "flock_holder": holder,
        "tick_socket": tick,
        "spool_pending": pending,
        "checks": checks,
        "ok": not hard,
        "failed_checks": [c["id"] for c in hard],
        "remediation": (
            "state_doctor.py repair --profile "
            + profile
            + "  (quarantine + fresh store; relaunch through "
              "crusoe-hermes-gateway-wrap.sh)"
        ) if hard else "",
    }


def census_all() -> list[dict[str, Any]]:
    root = agents_data_home()
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        home = entry / "profiles" / entry.name
        if not home.is_dir():
            home = entry
        if not (home / "config.yaml").exists() and not (home / "state.db").exists():
            continue
        rows.append(census_profile(entry.name))
    return rows


def preflight_profile(profile: str) -> dict[str, Any]:
    result = census_profile(profile)
    result["action"] = "preflight"
    return result


# ── repair ───────────────────────────────────────────────────────────────────

def pid_alive(pid: int) -> bool:
    return os.path.isdir(f"/proc/{pid}")


def terminate_writers(writers: list[dict[str, Any]], grace: float = 10.0) -> list[int]:
    """SIGTERM writers, wait up to `grace` seconds, SIGKILL survivors.
    Returns pids still alive afterwards."""
    for w in writers:
        try:
            os.kill(w["pid"], 15)  # SIGTERM
        except OSError:
            continue
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not any(pid_alive(w["pid"]) for w in writers):
            return []
        time.sleep(0.25)
    for w in writers:
        if pid_alive(w["pid"]):
            try:
                os.kill(w["pid"], 9)  # SIGKILL
            except OSError:
                continue
    time.sleep(0.5)
    return [w["pid"] for w in writers if pid_alive(w["pid"])]


def quarantine_bundle(home: Path) -> dict[str, str]:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M")
    moved: dict[str, str] = {}
    for key, path in db_paths(home).items():
        if not path.exists():
            continue
        target = path.with_name(f"{path.name}.malformed-{stamp}")
        seq = 1
        while target.exists():
            seq += 1
            target = path.with_name(f"{path.name}.malformed-{stamp}-{seq}")
        os.replace(path, target)
        moved[key] = str(target)
    return moved


def fresh_store(home: Path) -> dict[str, Any]:
    """Create a fresh state.db pinned to journal_mode=delete (P1)."""
    out: dict[str, Any] = {"created": False, "journal_mode": None,
                           "quick_check": None, "error": None}
    try:
        conn = sqlite3.connect(str(home / "state.db"))
        try:
            mode = conn.execute("PRAGMA journal_mode=DELETE").fetchone()
            out["journal_mode"] = mode[0] if mode else None
            # Force header materialization: a 0-byte file (no write yet) reads
            # back as malformed on the next probe.
            conn.execute("CREATE TABLE IF NOT EXISTS _state_doctor_probe (k INTEGER)")
            conn.execute("DROP TABLE _state_doctor_probe")
            conn.commit()
            out["created"] = True
            qc = conn.execute("PRAGMA quick_check").fetchone()
            out["quick_check"] = qc[0] if qc else None
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        out["error"] = str(exc)[:200]
    return out


def salvage_hint(quarantined: dict[str, str]) -> str:
    db = quarantined.get("db")
    if not db:
        return ""
    return (f"hermes sessions recover --source {db} "
            f"--output {db}.recovered --allow-partial")


def repair_profile(profile: str, confirm: bool, salvage: bool) -> dict[str, Any]:
    home = runtime_home(profile)
    store = classify_store(home)
    writers = live_writer_pids(home)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action": "repair",
        "profile": profile,
        "hermes_home": str(home),
        "pre": store,
        "steps": [],
        "quarantined": None,
        "fresh_store": None,
        "post": None,
        "salvage_hint": "",
        "refused": None,
        "ok": False,
    }
    healthy = store["status"] == "ok" and store.get("journal_mode") != "wal"
    if healthy:
        result["refused"] = "store is healthy and journal mode is not WAL; nothing to repair"
        return result
    if writers:
        if not confirm:
            result["refused"] = (
                "live writers present: "
                + ", ".join(f"pid={w['pid']} role={w['role']}" for w in writers)
                + " — stop them first (systemctl --user stop hermes-gateway-<profile>)"
            )
            return result
        result["steps"].append({"step": "terminate-writers", "detail": "SIGTERM then SIGKILL"})
        survivors = terminate_writers(writers)
        result["terminated_survivors"] = survivors
        writers = live_writer_pids(home)
        if writers:
            result["refused"] = "writers survived termination: " + repr([w["pid"] for w in writers])
            return result

    moved = quarantine_bundle(home)
    result["quarantined"] = moved
    result["steps"].append({"step": "quarantine", "moved": moved})
    if not moved.get("db"):
        result["error"] = "nothing quarantined — no db bundle on disk"
        return result

    fresh = fresh_store(home)
    result["fresh_store"] = fresh
    if fresh.get("created") and fresh.get("quick_check") == "ok":
        post = classify_store(home)
        result["post"] = post
        result["ok"] = post["status"] == "ok" and post.get("journal_mode") == "delete"
    else:
        result["ok"] = False
    result["salvage_hint"] = salvage_hint(moved)
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="state-doctor",
        description="Hermes profile state-store doctor (census/preflight/repair)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("census", help="read-only per-profile state report")
    c.add_argument("--profile", default=None)
    c.add_argument("--all", action="store_true",
                   help="census every profile under HERMES_AGENTS_DATA_HOME")

    p = sub.add_parser("preflight", help="launch gate for cosw / agents up")
    p.add_argument("--profile", required=True)

    r = sub.add_parser("repair", help="quarantine corrupt store; fresh DELETE-journal db")
    r.add_argument("--profile", required=True)
    r.add_argument("--yes", action="store_true", help="confirm destructive repair")
    r.add_argument("--salvage", action="store_true",
                   help="also attempt hermes sessions recover on the quarantined copy")

    args = parser.parse_args(argv)
    if args.cmd == "census":
        if args.all:
            payload: Any = census_all()
        elif args.profile:
            payload = census_profile(args.profile)
        else:
            parser.error("census needs --profile NAME or --all")
            return 2
        print(json.dumps(payload, indent=2, sort_keys=True))
        if isinstance(payload, dict):
            return 0 if payload.get("ok") else 1
        return 0 if all(row.get("ok") for row in payload) else 1

    if args.cmd == "preflight":
        payload = preflight_profile(args.profile)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1

    if args.cmd == "repair":
        if not args.yes:
            log("repair quarantines the live state.db bundle — rerun with --yes")
            return 2
        payload = repair_profile(args.profile, confirm=True, salvage=args.salvage)
        print(json.dumps(payload, indent=2, sort_keys=True))
        if payload.get("refused"):
            return 1
        return 0 if payload.get("ok") else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())