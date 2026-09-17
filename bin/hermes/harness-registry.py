#!/usr/bin/env python3
"""Load config/harness/registry.toml. Stdout JSON only; diagnostics on stderr."""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[2]
REGISTRY = PROFILE_DIR / "config" / "harness" / "registry.toml"


def load(path: Path | None = None) -> dict:
    src = path or REGISTRY
    data = tomllib.loads(src.read_text(encoding="utf-8"))
    if int(data.get("schema", 0)) != 1:
        raise SystemExit(f"unsupported registry schema: {data.get('schema')}")
    return data


def names(data: dict) -> list[str]:
    return sorted((data.get("harness") or {}).keys())


def host_classes(data: dict) -> list[str]:
    return sorted((data.get("hosts") or {}).keys())


def forks(data: dict) -> dict[str, dict]:
    return {k: v for k, v in (data.get("harness") or {}).items() if v.get("kind") == "fork"}


def pins(data: dict) -> dict[str, dict]:
    return {k: v for k, v in (data.get("harness") or {}).items() if v.get("kind") == "pin"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Emit harness registry as JSON")
    p.add_argument("--path", type=Path, default=REGISTRY)
    p.add_argument("--section", choices=["all", "policy", "hosts", "harness", "forks", "pins"], default="all")
    args = p.parse_args(argv)
    data = load(args.path)
    payload: object
    if args.section == "all":
        payload = data
    elif args.section == "forks":
        payload = forks(data)
    elif args.section == "pins":
        payload = pins(data)
    else:
        payload = data.get(args.section) or {}
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
