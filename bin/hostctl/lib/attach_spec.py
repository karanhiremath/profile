#!/usr/bin/env python3
"""Host/sandbox-agnostic attach grammar for agentic and interactive sessions.

    <kind>[-<instance>][-s] [--instance NAME] [--session NAME] [--family NAME] [session]

Kinds and instances come from inventory. Trailing ``-s`` is the sandbox
marker, not an instance named ``s``. Override instance ``s`` with
``--instance s``.

Examples:
    oma                 kind=oma instance=default session=home
    oma-default         same, instance title default
    oma-default cos     session=cos on instance default
    oma-s               sandbox on default oma
    oma-default-s       sandbox on instance default
    mac / mac-s         host tmux / host sandbox
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_KINDS = ("mac", "oma")
DEFAULT_INSTANCE = "default"
DEFAULT_SESSION_BY_KIND = {"mac": "mac", "oma": "home"}
DEFAULT_SANDBOX_POOL = (
    "nixos",
    "rust",
    "elixir",
    "mojo",
    "go",
    "python",
)
DEFAULT_PERSONAL_FAMILY = "nixos"
ALIAS_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class AttachSpec:
    kind: str
    instance: str
    sandbox: bool
    session: str
    family: str | None
    list_sessions: bool
    targets: tuple[str, ...]
    alias: str
    os_class: str
    role: str

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["targets"] = list(self.targets)
        return data


def _kinds(inventory: dict[str, Any] | None) -> tuple[str, ...]:
    attach = (inventory or {}).get("attach") or {}
    kinds = attach.get("kinds") or {}
    if isinstance(kinds, dict) and kinds:
        return tuple(str(k) for k in kinds)
    return DEFAULT_KINDS


def _session_default(kind: str, inventory: dict[str, Any] | None) -> str:
    attach = (inventory or {}).get("attach") or {}
    defaults = attach.get("defaults") or {}
    by_kind = defaults.get("session_by_kind") or DEFAULT_SESSION_BY_KIND
    if kind in by_kind:
        return str(by_kind[kind])
    return str(defaults.get("session") or DEFAULT_SESSION_BY_KIND.get(kind, "home"))


def _instance_default(inventory: dict[str, Any] | None) -> str:
    attach = (inventory or {}).get("attach") or {}
    defaults = attach.get("defaults") or {}
    return str(defaults.get("instance") or DEFAULT_INSTANCE)


def _kind_meta(kind: str, inventory: dict[str, Any] | None) -> tuple[str, str]:
    attach = (inventory or {}).get("attach") or {}
    kinds = attach.get("kinds") or {}
    meta = kinds.get(kind) or {}
    role = str(meta.get("role") or ("host" if kind == "mac" else "peer"))
    os_class = str(meta.get("os_class") or ("macos" if kind == "mac" else "omarchy"))
    return role, os_class


def _sandbox_pool(inventory: dict[str, Any] | None) -> tuple[str, ...]:
    attach = (inventory or {}).get("attach") or {}
    sandbox = attach.get("sandbox") or {}
    pool = sandbox.get("pool") or DEFAULT_SANDBOX_POOL
    return tuple(str(item) for item in pool if item and item != "project-selected")


def _personal_family(inventory: dict[str, Any] | None) -> str:
    attach = (inventory or {}).get("attach") or {}
    defaults = attach.get("defaults") or {}
    sandbox = attach.get("sandbox") or {}
    return str(
        sandbox.get("default_family")
        or defaults.get("personal_family")
        or DEFAULT_PERSONAL_FAMILY
    )


def pick_family(
    session: str,
    *,
    family: str | None = None,
    inventory: dict[str, Any] | None = None,
    persisted: str | None = None,
) -> str:
    if family:
        return family
    if persisted:
        return persisted
    personal = _personal_family(inventory)
    if personal:
        return personal
    pool = _sandbox_pool(inventory)
    if not pool:
        return DEFAULT_PERSONAL_FAMILY
    digest = hashlib.sha256(session.encode()).digest()
    return pool[int.from_bytes(digest[:2], "big") % len(pool)]


def parse_alias(token: str, inventory: dict[str, Any] | None = None) -> tuple[str, str | None, bool]:
    if not token or not ALIAS_TOKEN.match(token):
        raise ValueError(f"invalid attach alias: {token!r}")
    kinds = _kinds(inventory)
    sandbox = False
    core = token
    if token.endswith("-s"):
        sandbox = True
        core = token[:-2]
        if not core:
            raise ValueError(f"invalid attach alias: {token!r}")
    if core in kinds:
        return core, None, sandbox
    for kind in sorted(kinds, key=len, reverse=True):
        prefix = f"{kind}-"
        if core.startswith(prefix):
            instance = core[len(prefix) :]
            if instance:
                return kind, instance, sandbox
    raise ValueError(f"unknown attach alias: {token!r} (kinds: {', '.join(kinds)})")


def instance_targets(
    kind: str,
    instance: str,
    inventory: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    attach = (inventory or {}).get("attach") or {}
    instances = attach.get("instances") or {}
    row = instances.get(instance) or {}
    kind_row = row.get(kind) or {}
    targets = kind_row.get("targets")
    if targets:
        return tuple(str(item) for item in targets if item)
    hosts = (inventory or {}).get("hosts") or {}
    # Fall back to the peer host named in aliases, then well-known names.
    aliases = (inventory or {}).get("aliases") or {}
    peer = ((aliases.get("peer_tmux") or {}).get("khire-mac-mini") or {}).get(kind)
    if peer and peer in hosts:
        host = hosts[peer]
        fqdn = host.get("tailnet_fqdn")
        found = []
        if fqdn:
            found.append(str(fqdn))
        for item in host.get("ssh_fallbacks") or []:
            found.append(str(item).split(":")[0])
        if found:
            return tuple(found)
    if kind == "oma":
        return ("try-omarchy.tail1e8436.ts.net", "try-omarchy")
    return ()


def parse_argv(
    argv: list[str],
    inventory: dict[str, Any] | None = None,
) -> AttachSpec:
    if not argv:
        raise ValueError("attach alias required")
    parser = argparse.ArgumentParser(prog="attach", add_help=False)
    parser.add_argument("--instance")
    parser.add_argument("--session")
    parser.add_argument("--family")
    parser.add_argument("--ls", "-l", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    opts, rest = parser.parse_known_args(argv)
    if opts.help:
        raise SystemExit(0)
    if not rest:
        raise ValueError("attach alias required")
    alias = rest[0]
    extra = rest[1:]
    if opts.ls and extra:
        raise ValueError("--ls does not take a session name")
    positional_session = None
    for item in extra:
        if item in {"--ls", "-l"}:
            opts.ls = True
            continue
        if item.startswith("-"):
            raise ValueError(f"unknown attach flag: {item}")
        if positional_session is not None:
            raise ValueError("only one session name is allowed")
        positional_session = item
    kind, alias_instance, sandbox = parse_alias(alias, inventory)
    instance = opts.instance or alias_instance or _instance_default(inventory)
    session = opts.session or positional_session or _session_default(kind, inventory)
    family = None
    if sandbox:
        family = pick_family(session, family=opts.family, inventory=inventory)
    role, os_class = _kind_meta(kind, inventory)
    targets = instance_targets(kind, instance, inventory)
    return AttachSpec(
        kind=kind,
        instance=instance,
        sandbox=sandbox,
        session=session,
        family=family,
        list_sessions=bool(opts.ls),
        targets=targets,
        alias=alias,
        os_class=os_class,
        role=role,
    )


def load_inventory(path: Path) -> dict[str, Any]:
    text = path.read_text()
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return data
    except ImportError:
        # Grammar defaults live in this module. Inventory overlays need PyYAML.
        return {}
    return {}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    inventory_path = Path(
        next(
            (
                argv[i + 1]
                for i, item in enumerate(argv[:-1])
                if item in {"--inventory", "-I"}
            ),
            "",
        )
        or Path(__file__).resolve().parents[1] / "interactive.yaml"
    )
    cleaned = []
    skip = False
    for item in argv:
        if skip:
            skip = False
            continue
        if item in {"--inventory", "-I"}:
            skip = True
            continue
        cleaned.append(item)
    inventory = load_inventory(inventory_path) if inventory_path.exists() else {}
    spec = parse_argv(cleaned, inventory)
    json.dump(spec.as_json(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"attach: {exc}", file=sys.stderr)
        raise SystemExit(2)
