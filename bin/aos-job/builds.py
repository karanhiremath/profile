"""Reduce a trusted watcher journal; optionally run one claimed successor."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

TERMINAL = {"SUCCESS", "FAILURE", "TIMEOUT", "INTERNAL_ERROR", "CANCELLED", "EXPIRED"}


def board(journal):
    rows = {}
    try:
        source = journal.open(encoding="utf-8")
    except FileNotFoundError:
        return rows
    with source:
        for line in source:
            if not line.endswith("\n"):
                break  # append in flight
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("expected JSON object")
            build, label = event.get("uuid"), event.get("label")
            if not all(isinstance(v, str) and v for v in (build, label)):
                continue
            if event.get("event") not in ("build-found", "status", "terminal"):
                continue
            status = event.get("status")
            terminal = event["event"] == "terminal"
            if not isinstance(status, str) or not status:
                if terminal:
                    raise ValueError("terminal status missing")
                status = None
            if terminal and status not in TERMINAL:
                raise ValueError("unknown terminal status")
            key = (label, build)
            row = rows.setdefault(key, dict(label=label, buildId=build, status=None, digest=None, terminal=False))
            if row["terminal"]:
                if terminal and row["status"] != status:
                    raise ValueError("conflicting terminal statuses")
                continue
            if status:
                row.update(status=status, terminal=terminal)
            if terminal and isinstance(event.get("digest"), str):
                row["digest"] = event["digest"]
    return rows


def main(argv):
    sub, *argv = argv
    parser = argparse.ArgumentParser(prog=f"aos {sub}")
    parser.add_argument("--journal", type=Path, required=True, help="trusted per-case watcher JSONL")
    parser.add_argument("--label", required=sub == "chain")
    if sub == "builds":
        parser.add_argument("--case", help="case identifier to include in output")
        args = parser.parse_args(argv)
        if not args.journal.is_file():
            parser.error("journal not found")
        rows = board(args.journal)
        print(json.dumps([dict(rows[k], case=args.case) for k in sorted(rows) if args.label in (None, k[0])]))
        return 0
    parser.add_argument("--build-id", required=True, help="immutable watcher uuid, not just a label")
    parser.add_argument("--claims", type=Path, required=True, help="shared private claim directory for this case")
    parser.add_argument("--timeout", type=int, required=True, metavar="SECONDS")
    parser.add_argument("--poll", type=int, default=15, metavar="SECONDS")
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command or min(args.timeout, args.poll) < 1:
        parser.error("require a command after --, positive --timeout and positive --poll")
    deadline = time.monotonic() + args.timeout
    while True:
        row = board(args.journal).get((args.label, args.build_id))
        if row and row["terminal"]:
            if row["status"] != "SUCCESS":
                print(f"aos chain: build ended in {row['status']}; not launching", file=sys.stderr)
                return 4
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print("aos chain: timed out waiting for exact terminal record", file=sys.stderr)
            return 124
        time.sleep(min(args.poll, remaining))
    # Key by immutable build, not label, to avoid multiple aliases launching twice.
    claim = hashlib.sha256(args.build_id.encode()).hexdigest()
    args.claims.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        (args.claims / claim).mkdir(mode=0o700)
    except FileExistsError:
        print("aos chain: already claimed; not launching", file=sys.stderr)
        return 3
    # Retain claim even after a failed exec: no automatic retry of ambiguous side effects.
    os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError):
        print("aos: could not read watcher journal, claim, or execute successor; verify before retrying", file=sys.stderr)
        sys.exit(2)
