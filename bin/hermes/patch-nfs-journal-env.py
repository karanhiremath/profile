#!/usr/bin/env python3
"""Patch hermes-agent's hermes_state.py to honor HERMES_STATE_JOURNAL_MODE.

Upstream 0.18.2/0.21.0 apply_wal_with_fallback() always attempts
PRAGMA journal_mode=WAL and only falls back to DELETE when the pragma
RAISES. On a fresh/quiet NFS store the WAL attempt can SUCCEED, silently
re-enabling WAL on Vast NFS — the exact rot cycle that produced
state.db.malformed-20260914 and state.db.malformed-20260929 for
chief-of-staff-work (see agentic/infra/crusoe-hermes-homes.md, rule 1).

The contract env pin HERMES_STATE_JOURNAL_MODE=delete (exported by
crusoe-hermes-home.env.sh / crusoe-hermes-gateway-wrap.sh) is currently
UNIMPLEMENTED upstream. This patch inserts an env check at the top of
apply_wal_with_fallback: when the env requests a non-WAL journal mode,
set DELETE directly and skip the WAL attempt.

Idempotent: exits 0 without change if the marker is already present.
Run after every toolchain (re)install: bin/hermes/install calls it.
stdout is machine JSON only (Cartesia CLI pipeline contract).
"""
from __future__ import annotations

import json
import os
import py_compile
import sys
import sysconfig
from pathlib import Path

MARKER = "HERMES_STATE_JOURNAL_MODE_PATCH_V1"
ENV_SNIPPET = '''\
    # HERMES_STATE_JOURNAL_MODE_PATCH_V1 (profile/bin/hermes/patch-nfs-journal-env.py)
    # Contract pin: non-WAL journal requested via env — skip the WAL attempt
    # entirely. WAL on NFS/Vast is the state.db.malformed-* rot cycle.
    _requested_mode = os.environ.get("HERMES_STATE_JOURNAL_MODE", "").strip().lower()
    if _requested_mode and _requested_mode not in ("wal", ""):
        conn.execute("PRAGMA journal_mode=DELETE")
        return "delete"
'''


def venv_site_packages() -> Path:
    explicit = os.environ.get("HERMES_PYTHON_VENV")
    if explicit:
        return Path(explicit) / "lib"
    toolchain = os.environ.get("HERMES_TOOLCHAIN_HOME")
    if not toolchain:
        toolchain = f"{os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))}/hermes-toolchain"
    return Path(toolchain) / "venv" / "lib"


def find_hermes_state() -> Path | None:
    lib = venv_site_packages()
    candidates = sorted(lib.glob("python3.*/site-packages/hermes_state.py"))
    return candidates[0] if candidates else None


def patch_targets() -> list[Path]:
    """All hermes code planes that carry hermes_state.py.

    1. Toolchain venv site-packages (gateway / systemd service paths).
    2. Agent-root worktree overlays (herm/cosw TUI paths — fork-env.sh pins
       HERMES_AGENT_ROOT/PYTHONPATH to a timeout-free Cursor SDK worktree,
       which shadows site-packages on import).
    """
    targets: list[Path] = []
    lib = venv_site_packages()
    targets.extend(sorted(lib.glob("python3.*/site-packages/hermes_state.py")))
    agent_root = os.environ.get("HERMES_AGENT_ROOT")
    if agent_root:
        cand = Path(agent_root) / "hermes_state.py"
        if cand.is_file():
            targets.append(cand)
    worktrees = Path.home() / "src" / "hermes-agent-worktrees"
    if worktrees.is_dir():
        targets.extend(sorted(worktrees.glob("*/hermes_state.py")))
    # dedupe preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for t in targets:
        rp = t.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(t)
    return unique


def main() -> int:
    check_only = "--check" in sys.argv
    result: dict[str, object] = {
        "schema_version": "profile.hermes-journal-patch.v1",
        "action": "check" if check_only else "patch",
        "ok": False,
    }
    targets = patch_targets()
    if not targets:
        result["error"] = "no hermes_state.py found (venv or worktree overlays)"
        print(json.dumps(result))
        return 1
    overall_ok = True
    for target in targets:
        if check_only:
            text = target.read_text() if target.is_file() else ""
            outcome = {"target": str(target),
                       "ok": MARKER in text,
                       "status": "patched" if MARKER in text else "missing"}
        else:
            outcome = patch_one(target)
        overall_ok = overall_ok and bool(outcome.get("ok"))
        result.setdefault("targets", []).append(outcome)
    result["ok"] = overall_ok
    print(json.dumps(result))
    return 0 if overall_ok else 1


def patch_one(target: Path) -> dict[str, object]:
    outcome: dict[str, object] = {"target": str(target), "ok": False}
    try:
        text = target.read_text()
    except OSError as exc:
        outcome["error"] = str(exc)[:200]
        return outcome
    if MARKER in text:
        outcome["ok"] = True
        outcome["status"] = "already-patched"
        return outcome

    # Insert after the end of apply_wal_with_fallback's docstring, before the
    # read-only probe. The docstring ends with the first triple-quote after
    # 'def apply_wal_with_fallback('.
    fn_pos = text.find("def apply_wal_with_fallback(")
    if fn_pos < 0:
        outcome["error"] = "apply_wal_with_fallback not found — upstream changed?"
        return outcome
    doc_end = text.find('"""', fn_pos)
    if doc_end < 0:
        outcome["error"] = "docstring end not found"
        return outcome
    doc_end = text.find('"""', doc_end + 3)
    if doc_end < 0:
        outcome["error"] = "docstring close not found"
        return outcome
    insert_at = text.index("\n", doc_end) + 1
    patched = text[:insert_at] + ENV_SNIPPET + text[insert_at:]

    head = patched[: patched.find("def ")]
    if "import os" not in head:
        patched = patched.replace("import json\n", "import json\nimport os\n", 1)

    tmp = target.with_suffix(".py.patched")
    tmp.write_text(patched)
    try:
        py_compile.compile(str(tmp), doraise=True)
        tmp.replace(target)
    except (py_compile.PyCompileError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        outcome["error"] = str(exc)[:200]
        return outcome
    # byte-compiled cache invalidation
    cache = target.parent / "__pycache__"
    for pyc in cache.glob("hermes_state*.pyc"):
        pyc.unlink(missing_ok=True)

    outcome["ok"] = True
    outcome["status"] = "patched"
    outcome["verify"] = verify()
    return outcome


def verify() -> bool:
    """Functional check against the toolchain venv interpreter: with env=delete,
    apply_wal_with_fallback returns delete."""
    import sqlite3
    import subprocess

    venv_py = os.environ.get("HERMES_PYTHON_VENV")
    python = (Path(venv_py) / "bin" / "python") if venv_py else find_venv_python()
    if not python:
        return False
    code = (
        "import os, sqlite3, tempfile;"
        "os.environ['HERMES_STATE_JOURNAL_MODE']='delete';"
        "import hermes_state;"
        "c=sqlite3.connect(tempfile.mktemp(suffix='.db'));"
        "print(hermes_state.apply_wal_with_fallback(c, db_label='patch-verify'))"
    )
    proc = subprocess.run(
        [str(python), "-c", code], capture_output=True, text=True
    )
    return proc.returncode == 0 and proc.stdout.strip().endswith("delete")


def find_venv_python() -> Path | None:
    lib = venv_site_packages()  # <toolchain>/venv/lib
    venv_bin = lib.parent / "bin" / "python"
    return venv_bin if venv_bin.is_file() else None


if __name__ == "__main__":
    sys.exit(main())