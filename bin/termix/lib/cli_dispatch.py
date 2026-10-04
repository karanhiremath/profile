"""Classify `termix` wrapper argv: stack, official CLI, or host-tmux attach.

``termix <session>`` attaches when the first token is not a reserved
wrapper/CLI command. Reserved names stay on the official CLI; use
``termix attach <session>`` for those session names.
"""

from __future__ import annotations

import json
import sys

# Wrapper stack verbs handled in bin/termix/cli before this classifier.
WRAPPER = frozenset(
    {
        "up",
        "start",
        "down",
        "serve",
        "caddy",
        "status",
        "help",
        "-h",
        "--help",
    }
)

# Official @termix-cli/cli commands. Keep in sync with `termix --help`.
OFFICIAL = frozenset(
    {
        "login",
        "logout",
        "whoami",
        "hosts",
        "exec",
        "ssh",
        "files",
        "tunnel",
        "docker",
        "fleets",
        "sessions",
        "snippets",
        "credentials",
        "alerts",
        "audit-logs",
        "users",
        "api-keys",
        "version",
        "status",
        "help",
    }
)

ATTACH_EXPLICIT = "attach"
SNIPPETS_SYNC = frozenset({"snippets-sync", "sync-snippets"})


def classify(argv: list[str]) -> tuple[str, list[str]]:
    """Return ``(action, args)``.

    Actions: ``wrapper``, ``official``, ``attach``, ``snippets-sync``.
    """
    if not argv:
        return "official", []
    first = argv[0]
    if first in WRAPPER:
        return "wrapper", argv
    if first == "--":
        return "official", argv[1:]
    if first in SNIPPETS_SYNC:
        return "snippets-sync", argv[1:]
    if first == ATTACH_EXPLICIT:
        return "attach", argv[1:]
    if first in {"--ls", "-l"}:
        return "attach", argv
    if first.startswith("-"):
        return "official", argv
    if first in OFFICIAL:
        return "official", argv
    return "attach", argv


def reserved_session_names() -> frozenset[str]:
    """Session names that cannot use the ``termix <session>`` shorthand."""
    return WRAPPER | OFFICIAL | SNIPPETS_SYNC | {ATTACH_EXPLICIT, "--", "--ls", "-l"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    if argv and argv[0] == "--json":
        as_json = True
        argv = argv[1:]
    action, rest = classify(argv)
    if as_json:
        json.dump({"action": action, "args": rest}, sys.stdout)
        sys.stdout.write("\n")
        return 0
    sys.stdout.write(action + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
