#!/usr/bin/env python3
"""Anthropic API-key fan-out from the pi auth store to every Hermes home.

Canonical on-host store: ~/.pi/agent/auth.json ``anthropic`` entry with
``type: api_key`` (staged from 1Password by the operator; agents never call
op). Hermes resolves ANTHROPIC_API_KEY from each home's ``.env`` first, so
every home gets the key written there (0600). API keys are static — unlike
Codex OAuth grants there is no rotation race, so plain write-through is safe.

Never prints credential values. Output is counts, lengths and booleans only.

Env:
  PI_CODING_AGENT_DIR       pi agent dir (default ~/.pi/agent)
  HERMES_AGENTS_DATA_HOME   seat data home (default ~/.local/share/hermes-agents)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

ENV_VAR = "ANTHROPIC_API_KEY"


def pi_auth_path() -> Path:
    base = os.environ.get("PI_CODING_AGENT_DIR") or str(Path.home() / ".pi" / "agent")
    return Path(base).expanduser() / "auth.json"


def data_home() -> Path:
    if override := os.environ.get("HERMES_AGENTS_DATA_HOME"):
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hermes-agents"


def source_key() -> Optional[str]:
    try:
        entry = json.loads(pi_auth_path().read_text()).get("anthropic") or {}
    except (OSError, ValueError):
        return None
    if entry.get("type") != "api_key":
        return None
    key = str(entry.get("key") or "").strip()
    return key or None


def hermes_homes() -> List[Path]:
    """Every directory holding a Hermes config.yaml (root, profiles, seats)."""
    roots: List[Path] = [Path.home() / ".hermes"]
    roots += sorted((Path.home() / ".hermes" / "profiles").glob("*"))
    dh = data_home()
    if dh.is_dir():
        for seat in sorted(dh.iterdir()):
            roots.append(seat)
            roots += sorted((seat / "profiles").glob("*"))
    return [r for r in roots if (r / "config.yaml").is_file()]


def _write_env(path: Path, key: str) -> bool:
    """Set ENV_VAR in a dotenv file atomically; return True when changed."""
    lines = path.read_text().splitlines() if path.exists() else []
    want = f"{ENV_VAR}={key}"
    out, seen = [], False
    for line in lines:
        if line.startswith(f"{ENV_VAR}="):
            if not seen:
                out.append(want)
            seen = True
        else:
            out.append(line)
    if not seen:
        out.append(want)
    if out == lines:
        return False
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".env.")
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return True


def status(homes: Iterable[Path], key: Optional[str]) -> dict:
    rows = []
    for home in homes:
        env = home / ".env"
        present = env.exists() and any(
            l.startswith(f"{ENV_VAR}=") and len(l) > len(ENV_VAR) + 1 for l in env.read_text().splitlines()
        )
        match = bool(key) and env.exists() and f"{ENV_VAR}={key}" in env.read_text().splitlines()
        rows.append({"home": str(home), "present": present, "matches_source": match})
    return {"schema": "anthropic-key-sync.v1", "source_present": bool(key),
            "source_len": len(key or ""), "homes": rows}


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("adopt", "status"))
    args = ap.parse_args(argv)
    key = source_key()
    homes = hermes_homes()
    if args.command == "status":
        print(json.dumps(status(homes, key)))
        return 0
    if not key:
        print(json.dumps({"schema": "anthropic-key-sync.v1", "status": "fail",
                          "reason": "no anthropic api_key in pi auth store"}))
        return 1
    changed = [str(h) for h in homes if _write_env(h / ".env", key)]
    print(json.dumps({"schema": "anthropic-key-sync.v1", "status": "ok", "homes": len(homes),
                      "changed": len(changed), "source_len": len(key)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
