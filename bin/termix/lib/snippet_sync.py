"""Plan and apply Termix snippets for live host tmux sessions.

Unfiled (no folder). The iOS keyboard dock and home-screen widget only
list unfiled snippets or names that exist in ``GET /snippets/folders``.
A string folder like ``tmux`` with no folder record is invisible.

Session snippets are the zsh command you would type: ``cos``, ``mac``.
Key snippets send control/escape sequences (tmux prefix is C-a).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable

FOLDER = ""
MANAGED_PREFIX = "hostctl:attach"
KEYS_PREFIX = "hostctl:keys"
PHONE_S = "phone-s"
ESC = "\x1b"
CTRL_A = "\x01"
CTRL_G = "\x07"

# Easy names for phone keys. Prefix C-a is this host's tmux prefix.
KEY_SNIPPETS = (
    ("ctrl-g", CTRL_G, "Ctrl-G"),
    ("panes", CTRL_A + "q", "tmux display-panes"),
    ("zoom", CTRL_A + "z", "tmux zoom pane"),
    ("esc", ESC, "escape"),
    ("wq", ESC + ":wq", "vim :wq"),
    ("w", ESC + ":w", "vim :w"),
    ("q", ESC + ":q", "vim :q"),
    ("q!", ESC + ":q!", "vim :q!"),
    ("palette", ESC + ":Telescope commands", "nvim command palette"),
)

# Home widget shows at most 12; small tiles show ~2.
PRIORITY = tuple(name for name, _content, _desc in KEY_SNIPPETS) + (
    "cos",
    "mac",
    "notes",
    "phone-s",
    "pi-p",
    "termix",
)

Runner = Callable[[list[str]], Any]


def normalize_folder(value: Any) -> str:
    return str(value or "").strip()


def snippet_content(session: str) -> str:
    return session


def sandbox_content() -> str:
    return PHONE_S


def key_snippets() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, content, desc in KEY_SNIPPETS:
        rows.append(
            {
                "name": name,
                "folder": FOLDER,
                "content": content,
                "description": f"{KEYS_PREFIX} {name} — {desc}",
            }
        )
    return rows


def desired_snippets(sessions: list[str]) -> list[dict[str, Any]]:
    rows = key_snippets()
    seen = {row["name"] for row in rows}
    for name in sessions:
        if not name or name == PHONE_S or name in seen:
            continue
        seen.add(name)
        rows.append(
            {
                "name": name,
                "folder": FOLDER,
                "content": snippet_content(name),
                "description": f"{MANAGED_PREFIX} mac {name}",
            }
        )
    rows.append(
        {
            "name": PHONE_S,
            "folder": FOLDER,
            "content": sandbox_content(),
            "description": f"{MANAGED_PREFIX} mac-s",
        }
    )
    rank = {name: index for index, name in enumerate(PRIORITY)}
    rows.sort(key=lambda row: (rank.get(row["name"], len(PRIORITY)), row["name"]))
    for index, row in enumerate(rows):
        row["order"] = index
    return rows


def is_managed(row: dict[str, Any]) -> bool:
    description = str(row.get("description") or "")
    return description.startswith("hostctl:")


def needs_update(have: dict[str, Any], want: dict[str, Any]) -> bool:
    if str(have.get("content") or "") != want["content"]:
        return True
    if str(have.get("description") or "") != want["description"]:
        return True
    if normalize_folder(have.get("folder")) != normalize_folder(want.get("folder")):
        return True
    return False


def folder_blocks_widgets(have: dict[str, Any]) -> bool:
    """True when a managed snippet is hidden from the iOS keyboard dock."""
    return bool(normalize_folder(have.get("folder")))


def plan(
    sessions: list[str],
    existing: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    desired = desired_snippets(sessions)
    desired_by_name = {row["name"]: row for row in desired}
    have_managed = {str(row.get("name") or ""): row for row in existing if is_managed(row)}
    create: list[dict[str, Any]] = []
    update: list[dict[str, Any]] = []
    delete: list[dict[str, Any]] = []
    for want in desired:
        have = have_managed.get(want["name"])
        if have is None:
            create.append(want)
            continue
        if folder_blocks_widgets(have) or int(have.get("order") or 0) != int(want["order"]):
            delete.append(have)
            create.append(want)
            continue
        if needs_update(have, want):
            update.append({**want, "id": have.get("id")})
    for name, have in have_managed.items():
        if name not in desired_by_name:
            delete.append(have)
    return {"create": create, "update": update, "delete": delete}


def parse_snippet_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("snippets") or payload.get("items") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def list_tmux_sessions(tmux: str = "tmux") -> list[str]:
    proc = subprocess.run(
        [tmux, "list-sessions", "-F", "#{session_name}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def official_runner(cli: str) -> Runner:
    def run(args: list[str]) -> Any:
        cmd = [cli, "--json", *args]
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        text = proc.stdout.strip()
        if not text:
            return {}
        return json.loads(text)

    return run


def _create_args(row: dict[str, Any]) -> list[str]:
    args = [
        "snippets",
        "create",
        "--name",
        row["name"],
        "--content",
        row["content"],
        "--description",
        row["description"],
    ]
    folder = normalize_folder(row.get("folder"))
    if folder:
        args.extend(["--folder", folder])
    return args


def _update_args(row: dict[str, Any]) -> list[str]:
    args = [
        "snippets",
        "update",
        "--name",
        row["name"],
        "--content",
        row["content"],
        "--description",
        row["description"],
        str(row["id"]),
    ]
    folder = normalize_folder(row.get("folder"))
    if folder:
        args[2:2] = ["--folder", folder]
    return args


def apply_plan(planned: dict[str, list[dict[str, Any]]], runner: Runner) -> dict[str, int]:
    counts = {"create": 0, "update": 0, "delete": 0}
    for row in planned["delete"]:
        runner(["snippets", "delete", str(row["id"])])
        counts["delete"] += 1
    for row in planned["create"]:
        runner(_create_args(row))
        counts["create"] += 1
    for row in planned["update"]:
        runner(_update_args(row))
        counts["update"] += 1
    return counts


def sync(
    *,
    runner: Runner,
    sessions: list[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    existing = parse_snippet_list(runner(["snippets", "list"]))
    planned = plan(sessions, existing)
    result: dict[str, Any] = {
        "folder": FOLDER or "(unfiled)",
        "sessions": sessions,
        "dry_run": dry_run,
        "plan": {
            "create": [row.get("name") for row in planned["create"]],
            "update": [row.get("name") for row in planned["update"]],
            "delete": [row.get("name") for row in planned["delete"]],
        },
    }
    if dry_run:
        result["applied"] = {"create": 0, "update": 0, "delete": 0}
        return result
    result["applied"] = apply_plan(planned, runner)
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = False
    for item in argv:
        if item in {"--dry-run", "-n"}:
            dry_run = True
    cli = os.environ.get("TERMIX_OFFICIAL") or os.environ.get("TERMIX_CLI") or "termix"
    tmux = os.environ.get("TERMIX_TMUX") or "tmux"
    sessions = list_tmux_sessions(tmux)
    result = sync(runner=official_runner(cli), sessions=sessions, dry_run=dry_run)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        raise SystemExit(exc.returncode or 1)
