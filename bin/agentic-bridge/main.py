#!/usr/bin/env python3
"""Project-scoped, append-only JSONL bridge. No transport or agent execution."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

SCHEMA = "agentic.bridge.v1"
PRIVACIES = ("personal", "work-private", "generic")
ACK_KINDS = {"ack", "assignment.accepted"}
MAX_BODY_BYTES = 64 * 1024


class BridgeError(Exception):
    """Invalid input or an unsafe bus operation."""


def check_envelope(event: object, project: str, privacy: str) -> dict:
    if not isinstance(event, dict) or event.get("schema_version") != SCHEMA:
        raise BridgeError("record is not an agentic.bridge.v1 envelope")
    if event.get("project") != project or event.get("privacy") != privacy:
        raise BridgeError("bus project/privacy mismatch; use a separate bus")
    for name in ("event_id", "timestamp", "sender", "recipient", "kind"):
        if not isinstance(event.get(name), str) or not event[name].strip():
            raise BridgeError(f"record requires a nonempty {name}")
    try:
        uuid.UUID(event["event_id"])
        stamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("not UTC")
    except ValueError as exc:
        raise BridgeError("record requires a UUID event_id and UTC timestamp") from exc
    if "in_reply_to" not in event or (
        event["in_reply_to"] is not None and not isinstance(event["in_reply_to"], str)
    ):
        raise BridgeError("record requires in_reply_to as null or a string")
    if not isinstance(event.get("body"), str):
        raise BridgeError("record body must be a string")
    if "correlation_id" in event and not isinstance(event["correlation_id"], str):
        raise BridgeError("correlation_id must be a string")
    if event["kind"] in ACK_KINDS and not event["in_reply_to"]:
        raise BridgeError("an acknowledgment requires in_reply_to")
    return event


def parse_bus(data: bytes, project: str, privacy: str) -> tuple[list[dict], bool]:
    """Return complete records; an unterminated final line is never accepted."""
    partial = bool(data) and not data.endswith(b"\n")
    lines = data.split(b"\n")[:-1]
    events: list[dict] = []
    ids: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        try:
            event = check_envelope(json.loads(line), project, privacy)
        except (ValueError, UnicodeError, BridgeError) as exc:
            raise BridgeError(f"invalid complete record at line {line_number}: {exc}") from exc
        if event["event_id"] in ids:
            raise BridgeError(f"duplicate event_id at line {line_number}")
        ids.add(event["event_id"])
        events.append(event)
    return events, partial


@contextmanager
def locked_bus(bus: Path, writable: bool):
    if bus.is_symlink() or bus.parent.is_symlink():
        raise BridgeError("bus and its runtime directory must not be symlinks")
    if writable:
        bus.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(bus.parent, 0o700)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND if writable else os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(bus, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BridgeError("bus must be a regular file")
        lock = fcntl.LOCK_EX if writable else fcntl.LOCK_SH
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(fd, lock | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise BridgeError("timed out waiting for the bus lock")
                time.sleep(0.01)
        if writable:
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r+b" if writable else "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def append_event(bus: Path, event: dict) -> dict:
    project, privacy = event["project"], event["privacy"]
    check_envelope(event, project, privacy)
    if len(event["body"].encode("utf-8")) > MAX_BODY_BYTES:
        raise BridgeError("body exceeds 64 KiB")
    with locked_bus(bus, writable=True) as stream:
        events, partial = parse_bus(stream.read(), project, privacy)
        if partial:
            raise BridgeError("bus has an unterminated final line; inspect/repair it before appending")
        if any(item["event_id"] == event["event_id"] for item in events):
            raise BridgeError("event_id already exists")
        if event["kind"] in ACK_KINDS and not any(
            item["event_id"] == event["in_reply_to"] for item in events
        ):
            raise BridgeError("acknowledgment target is not present in this bus")
        encoded = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        stream.seek(0, os.SEEK_END)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "posted", "event_id": event["event_id"], "event": event}


def read_bus(bus: Path, project: str, privacy: str) -> tuple[list[dict], bool]:
    with locked_bus(bus, writable=False) as stream:
        return parse_bus(stream.read(), project, privacy)


def summarize(events: list[dict], partial: bool) -> dict:
    posted = [event for event in events if event["kind"] not in ACK_KINDS]
    known = {event["event_id"] for event in events}
    acknowledgments = [event for event in events if event["kind"] in ACK_KINDS]
    acknowledged = {event["in_reply_to"] for event in acknowledgments}
    return {
        "events": len(events),
        "posted": len(posted),
        "acknowledgments": len(acknowledgments),
        "acknowledged": sum(event["event_id"] in acknowledged for event in posted),
        "unacknowledged_event_ids": [event["event_id"] for event in posted if event["event_id"] not in acknowledged],
        "orphan_acknowledgment_ids": [event["event_id"] for event in acknowledgments if event["in_reply_to"] not in known],
        "last_event_id": events[-1]["event_id"] if events else None,
        "trailing_partial_ignored": partial,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("append", "read", "status"):
        command = commands.add_parser(name)
        command.add_argument("--bus", type=Path, required=True)
        command.add_argument("--project", required=True)
        command.add_argument("--privacy", choices=PRIVACIES, required=True)
        if name == "append":
            for field in ("sender", "recipient", "kind"):
                command.add_argument(f"--{field}", required=True)
            command.add_argument("--in-reply-to")
            command.add_argument("--correlation-id")
            body = command.add_mutually_exclusive_group(required=True)
            body.add_argument("--body-file", type=Path)
            body.add_argument("--message", help="Short message, at most 2,000 characters")
        elif name == "read":
            command.add_argument("--after-event-id", help="Return only events after this event")
            command.add_argument("--limit", type=int, default=20, help="Maximum records (default: 20)")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if not args.project.strip():
            raise BridgeError("project must not be empty")
        bus = args.bus.expanduser().absolute()
        if args.command == "append":
            if args.body_file:
                with args.body_file.expanduser().open("rb") as source:
                    raw = source.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise BridgeError("body exceeds 64 KiB")
                body = raw.decode("utf-8")
            else:
                body = args.message
                if len(body) > 2000:
                    raise BridgeError("--message exceeds 2,000 characters; use --body-file")
            event = {
                "schema_version": SCHEMA,
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "project": args.project,
                "privacy": args.privacy,
                "sender": args.sender,
                "recipient": args.recipient,
                "kind": args.kind,
                "in_reply_to": args.in_reply_to,
                "body": body,
            }
            if args.correlation_id is not None:
                event["correlation_id"] = args.correlation_id
            output = append_event(bus, event)
        else:
            events, partial = read_bus(bus, args.project, args.privacy)
            if args.command == "status":
                output = summarize(events, partial)
            else:
                if args.limit < 1:
                    raise BridgeError("--limit must be positive")
                if args.after_event_id:
                    ids = [event["event_id"] for event in events]
                    if args.after_event_id not in ids:
                        raise BridgeError("--after-event-id is not present in this bus")
                    events = events[ids.index(args.after_event_id) + 1:]
                selected = events[:args.limit] if args.after_event_id else events[-args.limit:]
                output = {
                    "events": selected,
                    "last_event_id": selected[-1]["event_id"] if selected else args.after_event_id,
                    "has_more": len(events) > len(selected),
                    "trailing_partial_ignored": partial,
                }
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (BridgeError, OSError, UnicodeError) as exc:
        print(f"agentic-bridge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
