"""JSON-only CLI entrypoints; operations never fall through to legacy sync."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from typing import Any

from . import notes, oracle
from .core import Rejected, emit, event_fds, read_json


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default error includes untrusted argument values.
        raise Rejected("invalid_arguments")


def run(operation: str, execute: Callable[[], dict[str, Any]], help_text: str) -> None:
    fds: list[int] = []
    code = 0
    try:
        fds = event_fds()
        if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
            payload = {
                "schema_version": 1,
                "operation": operation,
                "state": "help",
                "usage": help_text,
                "publication_enabled": False,
            }
        else:
            payload = execute()
    except Rejected as exc:
        payload = {
            "schema_version": 1,
            "operation": operation,
            "state": "rejected",
            "reason": str(exc),
        }
        code = 2
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError):
        payload = {
            "schema_version": 1,
            "operation": operation,
            "state": "rejected",
            "reason": "evidence_unavailable",
        }
        code = 2
    emit(payload, fds)
    raise SystemExit(code)


def notes_main() -> None:
    def execute() -> dict[str, Any]:
        parser = Parser(add_help=False)
        parser.add_argument("command", choices=["status", "plan", "run"])
        parser.add_argument("--config", default=os.environ.get("AGENTIC_SYNC_NOTES_CONFIG"))
        parser.add_argument("--checkout")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--publish", action="store_true")
        parser.add_argument("--format", choices=["json"], default="json")
        args = parser.parse_args()
        if args.publish or (args.command == "run" and not args.dry_run):
            raise Rejected("publication_disabled_use_dry_run")
        if not args.config:
            raise Rejected("config_required")
        return notes.plan(
            read_json(args.config), args.checkout, f"agentic-sync.notes.{args.command}"
        )

    run(
        "agentic-sync.notes",
        execute,
        "agentic-sync notes {status|plan|run --dry-run} --config <json|-> "
        "[--checkout <absolute-root>] [--format json]; --publish is disabled",
    )


def oracle_main() -> None:
    def execute() -> dict[str, Any]:
        parser = Parser(add_help=False)
        parser.add_argument("command", choices=["inspect", "routes"])
        parser.add_argument("--registry", default=os.environ.get("REPO_CONTEXT_REGISTRY"))
        parser.add_argument("--repo")
        parser.add_argument("--route")
        parser.add_argument("--proposal-file")
        parser.add_argument("--checkout")
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--audience", choices=["private", "public"], default="private")
        parser.add_argument("--format", choices=["json"], default="json")
        args = parser.parse_args()
        if not args.registry:
            raise Rejected("registry_required")
        if args.registry == "-" and args.proposal_file == "-":
            raise Rejected("stdin_may_have_only_one_payload")
        data = read_json(args.registry)
        if args.command == "routes":
            entries = oracle.registry(data)
            if args.audience == "public":
                raise Rejected("registry_inventory_is_private")
            return {
                "schema_version": 1,
                "operation": "repo-context.routes",
                "state": "ok",
                "routes": [
                    {k: e[k] for k in ("repo", "routes", "owner_project", "checkout_env")}
                    for e in entries
                ],
            }
        if bool(args.repo) == bool(args.route) or not args.proposal_file:
            raise Rejected("repo_or_route_and_proposal_required")
        return oracle.inspect(
            data,
            read_json(args.proposal_file),
            args.repo or args.route,
            args.checkout,
            args.refresh,
            args.audience,
        )

    run(
        "repo-context",
        execute,
        "repo-context inspect --registry <json|-> {--repo <owner/name>|--route <alias>} "
        "--proposal-file <json|-> [--checkout <absolute-root>] [--refresh] "
        "[--audience private|public] [--format json]; repo-context routes --registry <json|->",
    )
