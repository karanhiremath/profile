"""Structured offline CLI. No live backend, credentials, audio, SSH or tmux calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import core, events, renderer


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise core.Rejected("invalid_arguments", "Invalid arguments; use --help.")

    def print_help(self, file: Any = None) -> None:
        super().print_help(file=file or sys.stderr)


def parser() -> Parser:
    root = Parser(
        prog="aos voice",
        description="Offline fake conference only; no live sessions, microphone or managed-agent connection.",
    )
    subs = root.add_subparsers(dest="command", required=True)
    for name in ("status", "doctor", "renderer"):
        subs.add_parser(name)
    targets = subs.add_parser(
        "targets", help="Read a fake catalog from stdin or --catalog."
    )
    targets.add_argument("--catalog", type=Path)
    for name in ("bind", "connect", "join", "disconnect", "leave", "dispatch"):
        cmd = subs.add_parser(name)
        modes = cmd.add_mutually_exclusive_group(required=True)
        modes.add_argument(
            "--fake",
            action="store_true",
            help="Simulate in pipeline state, never execute against a real session.",
        )
        modes.add_argument(
            "--dry-run",
            action="store_true",
            help="Return a plan without changing binding/connection/replay state.",
        )
        if name == "bind":
            cmd.add_argument("--domain", choices=("personal", "work"), required=True)
            cmd.add_argument("--target", required=True)
            cmd.add_argument("--generation", type=int, required=True)
        if name == "dispatch":
            cmd.add_argument(
                "--request",
                type=Path,
                required=True,
                help="Structured fake managed-agent tool callback; text is never echoed.",
            )
    return root


def read(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        with path.open("r", encoding="utf-8") as stream:
            raw = stream.read(core.LIMIT + 1)
    else:
        core.require(not sys.stdin.isatty(), "stdin_required")
        raw = sys.stdin.read(core.LIMIT + 1)
    return core.decode(raw)


def status() -> dict[str, Any]:
    return {
        "schema": "aos.voice.status.v1",
        "mode": "fake",
        "offline_ready": True,
        "live_ready": False,
        "microphone": False,
        "managed_agent_connected": False,
        "remote_discovery": False,
        "credential_access": False,
        "gates": [
            "maintained-voice-owner",
            "managed-agent-api-and-domain-approval",
            "authenticated-session-registry",
            "libghostty-wasm-api-and-license",
            "local-microphone-consent",
            "live-host-canary-approval",
        ],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"status", "doctor"}:
        return status()
    if args.command == "renderer":
        return renderer.capabilities()
    if args.command == "targets":
        return core.initial(read(args.catalog))
    value = read()
    if args.command == "bind":
        return core.bind(value, args.target, args.generation, args.domain, args.dry_run)
    if args.command in {"connect", "join", "disconnect", "leave"}:
        op = "connect" if args.command in {"connect", "join"} else "disconnect"
        return core.connection(value, op, args.dry_run)
    return core.FakeManagedAgent().call(value, read(args.request), args.dry_run)


def main(argv: list[str] | None = None) -> int:
    paths: list[Path] = []
    operation = "validate"
    try:
        args = parser().parse_args(argv)
        operation = args.command
        paths = events.sinks(dict(os.environ))
        result = run(args)
        events.emit(
            paths, operation, "dry_run" if getattr(args, "dry_run", False) else "done"
        )
        json.dump(result, sys.stdout, separators=(",", ":"), allow_nan=False)
        sys.stdout.write("\n")
        return 0
    except (
        core.Rejected,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
    ) as error:
        if not isinstance(error, core.Rejected):
            error = core.Rejected(
                "invalid_input", "Cannot process input; see the offline voice contract."
            )
        try:
            events.emit(paths, operation, "failed")
        except (core.Rejected, OSError):
            pass
        json.dump(
            {"schema": "aos.voice.error.v1", "ok": False, "code": error.code},
            sys.stdout,
        )
        sys.stdout.write("\n")
        print(f"aos voice: {error.message}", file=sys.stderr)
        return 2
