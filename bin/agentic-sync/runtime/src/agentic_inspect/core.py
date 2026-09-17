"""Bounded read-only primitives. Never surface subprocess output on errors."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

MAX_JSON = 1_000_000
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
SECRET_PATH = re.compile(
    r"(^|[/_.-])(auth|credential[s]?|secret[s]?|token[s]?|password[s]?|"
    r"sessions?|caches?|logs?|kubeconfig)([/_.-]|$)|"
    r"(^|/)\.env($|\.)|\.(pem|key|p12|pfx|sqlite|db)$|(^|/)id_(rsa|ed25519)$",
    re.IGNORECASE,
)


class Rejected(Exception):
    """A static reason code, never untrusted diagnostic text."""


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(source: str) -> Any:
    try:
        if source == "-":
            raw = sys.stdin.buffer.read(MAX_JSON + 1)
        else:
            with Path(source).open("rb") as stream:
                raw = stream.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise Rejected("input_too_large")
        return json.loads(raw, object_pairs_hook=unique_keys)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise Rejected("invalid_json") from exc


def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate_json_key")
        result[key] = value
    return result


def object_keys(data: Any, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(data, dict):
        raise Rejected("invalid_schema")
    if not required <= data.keys() or data.keys() - required - (optional or set()):
        raise Rejected("invalid_schema")


def schema_version(data: dict[str, Any]) -> None:
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise Rejected("unsupported_schema")


def repo_id(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 200 or not REPO.fullmatch(value):
        raise Rejected("invalid_repo_id")
    if any(part in {".", ".."} for part in value.split("/")):
        raise Rejected("invalid_repo_id")
    return value


def relpath(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise Rejected("invalid_relative_path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in {".", "..", ".git"} for part in path.parts)
        or value.startswith(("~", "-"))
        or "\\" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise Rejected("invalid_relative_path")
    return value


def path_list(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > 256 or (not value and not allow_empty):
        raise Rejected("invalid_path_list")
    paths = [relpath(item) for item in value]
    if len(set(paths)) != len(paths):
        raise Rejected("duplicate_path")
    return paths


def display_path(value: str) -> str | None:
    try:
        return None if SECRET_PATH.search(value) else relpath(value)
    except Rejected:
        return None


def visible_paths(values: list[str]) -> dict[str, Any]:
    safe = [path for item in values if (path := display_path(item)) is not None]
    return {"paths": safe, "redacted_count": len(values) - len(safe)}


def overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def command(args: list[str], *, limit: int = 4_000_000) -> bytes:
    # Ambient GIT_* can redirect an otherwise correct -C operation to a different
    # index/worktree/config. Do not allow it, and never prompt for credentials.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    try:
        result = subprocess.run(args, env=env, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Rejected("evidence_unavailable") from exc
    if result.returncode or len(result.stdout) > limit:
        raise Rejected("evidence_unavailable")
    return result.stdout


def remote_identity(url: str) -> str | None:
    # Deliberately reject userinfo/tokens, local remotes, alternate hosts and ports.
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([^\s]+?)(?:\.git)?", url)
    if not match:
        return None
    try:
        return repo_id(match[1])
    except Rejected:
        return None


class Git:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.prefix = [
            "git",
            "--no-optional-locks",
            "--no-replace-objects",
            "-C",
            str(self.root),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.pager=",
        ]
        top = Path(self.text("rev-parse", "--show-toplevel")).resolve()
        if top != self.root:
            raise Rejected("checkout_root_required")
        # Git status can invoke configured clean/process filters. Empty both
        # before any content-related operation; fsmonitor is already disabled.
        names = self.raw("config", "--null", "--name-only", "--list").decode().split("\0")
        for name in names:
            if name.startswith("filter.") and name.endswith((".clean", ".process", ".required")):
                value = "false" if name.endswith(".required") else ""
                self.prefix.extend(["-c", f"{name}={value}"])

    def raw(self, *args: str) -> bytes:
        return command([*self.prefix, *args])

    def text(self, *args: str) -> str:
        return self.raw(*args).decode("utf-8").strip()

    def optional(self, *args: str) -> str | None:
        try:
            return self.text(*args)
        except Rejected:
            return None

    def verify(self, expected: str) -> None:
        urls = self.text("remote", "get-url", "--all", "origin").splitlines()
        if len(urls) != 1 or remote_identity(urls[0]) != expected:
            raise Rejected("repository_identity_mismatch")
        push_urls = self.text("remote", "get-url", "--push", "--all", "origin").splitlines()
        if len(push_urls) != 1 or remote_identity(push_urls[0]) != expected:
            raise Rejected("push_identity_mismatch")

    def head(self) -> str:
        return self.text("rev-parse", "--verify", "HEAD")

    def branch(self) -> str | None:
        return self.optional("symbolic-ref", "--quiet", "--short", "HEAD")

    def changes(self) -> list[dict[str, str]]:
        records = (
            self.raw(
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--ignore-submodules=all",
            )
            .decode("utf-8")
            .split("\0")
        )
        changes: list[dict[str, str]] = []
        index = 0
        while index < len(records) and records[index]:
            record = records[index]
            if len(record) < 4 or record[2] != " ":
                raise Rejected("invalid_git_status")
            entry = {"status": record[:2], "path": record[3:]}
            if "R" in record[:2] or "C" in record[:2]:
                index += 1
                entry["original_path"] = records[index]
            changes.append(entry)
            index += 1
        return changes

    def diff_paths(self, base: str, tip: str) -> list[str]:
        # Only internally obtained object IDs are used as revision arguments.
        if not all(re.fullmatch(r"[0-9a-f]{40,64}", value) for value in (base, tip)):
            raise Rejected("invalid_object_id")
        data = self.raw(
            "diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", f"{base}...{tip}", "--"
        )
        return [p for p in data.decode("utf-8").split("\0") if p]


def checkout(env_name: Any, override: str | None) -> Path:
    if not isinstance(env_name, str) or not ENV_NAME.fullmatch(env_name):
        raise Rejected("invalid_checkout_env")
    value = override if override is not None else os.environ.get(env_name)
    if not value or not Path(value).is_absolute():
        raise Rejected("checkout_not_configured")
    try:
        return Path(value).resolve(strict=True)
    except OSError as exc:
        raise Rejected("checkout_unavailable") from exc


def safe_file(root: Path, relative: str) -> str | None:
    """Inspect metadata only. Never dereference symlinks or open note bodies."""
    parts = PurePosixPath(relative).parts
    node = root
    for index, part in enumerate(parts):
        node = node / part
        try:
            mode = node.lstat().st_mode
            if stat.S_ISLNK(mode):
                return "symlink"
            if index < len(parts) - 1:
                if not stat.S_ISDIR(mode) or (node / ".git").exists():
                    return "nested_repository_or_non_directory"
            elif not stat.S_ISREG(mode):
                return "non_regular_file"
        except FileNotFoundError:
            return "missing_or_deleted"
    return None


def event_fds() -> list[int]:
    """Explicit inherited pipe/socket sinks only; never create files or sockets."""
    spec = os.environ.get("CARTESIA_EVENT_SINKS", "")
    if not spec:
        return []
    result: list[int] = []
    for item in spec.split(","):
        if not re.fullmatch(r"fd:[0-9]+", item):
            raise Rejected("unsupported_event_sink")
        fd = int(item[3:])
        if fd < 3 or fd > 1_048_576 or fd in result:
            raise Rejected("invalid_event_sink")
        try:
            mode = os.fstat(fd).st_mode
        except OSError as exc:
            raise Rejected("invalid_event_sink") from exc
        if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
            raise Rejected("event_sink_must_be_pipe_or_socket")
        result.append(fd)
    return result


def emit(payload: dict[str, Any], fds: list[int]) -> None:
    # Side-channel schema intentionally contains no repo/path/proposal/error text.
    event = (
        json.dumps(
            {
                "schema_version": 1,
                "event": "inspection_finished",
                "operation": payload["operation"],
                "state": payload["state"],
            }
        )
        + "\n"
    )
    for fd in fds:
        try:
            os.write(fd, event.encode())
        except OSError:
            print("event_sink_unavailable", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
