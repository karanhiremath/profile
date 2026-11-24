"""Allowlisted auth events and a read-only status hook for fleet dashboards."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from run import publish

KINDS = {"auth.refreshed", "auth.expiring", "auth.needs-login", "auth.failed", "auth.recovered"}
URGENT = {"auth.needs-login", "auth.failed"}
NAME = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
SESSION = rf"(?:(?:aws|gcp|grant):{NAME}|aws:base:{NAME})"
IDENTITY = r"(?:[\w.+-]+@[\w.-]+|arn:aws(?:-[a-z-]+)?:iam::[0-9]{12}:role/[\w+=,.@/-]+)"


def iso(raw):
    if not isinstance(raw, str) or len(raw) > 40:
        raise ValueError
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.isoformat()


def validate(raw):
    if not isinstance(raw, dict) or set(raw) != {"id", "type", "session", "ts", "identity", "expires_at", "login"}:
        raise ValueError
    if not re.fullmatch(r"[0-9]{20}-[a-f0-9]{32}", raw["id"]) or raw["type"] not in KINDS:
        raise ValueError
    if not re.fullmatch(SESSION, raw["session"]):
        raise ValueError
    identity = raw["identity"]
    if identity is not None and (len(identity) > 256 or not re.fullmatch(IDENTITY, identity, re.ASCII)):
        raise ValueError
    expires = raw["expires_at"]
    fields = dict(type=raw["type"], session=raw["session"], ts=iso(raw["ts"]), identity=identity,
                  expiresAt=iso(expires) if expires is not None else None)
    if raw["type"] == "auth.needs-login":
        if raw["session"] == "gcp:base" and raw["login"] == "gcp":
            fields["operatorCommand"] = "cauth gcp session login --force"
        elif raw["session"].startswith("aws:base:") and raw["login"] in {"aws", "aws-sso"}:
            profile = shlex.quote(raw["session"].split(":")[-1])
            prefix = "aws sso login" if raw["login"] == "aws-sso" else "aws login"
            fields["operatorCommand"] = f"{prefix} --profile {profile}"
        else:
            raise ValueError
    elif raw["login"] is not None:
        raise ValueError
    return fields


def event(argv):
    parser = argparse.ArgumentParser(prog="aos job auth-event")
    route = parser.add_mutually_exclusive_group(required=True)
    route.add_argument("--target-sid")
    route.add_argument("--global-only", action="store_true")
    parser.add_argument("--inbox", type=Path)
    args = parser.parse_args(argv)
    if args.target_sid and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", args.target_sid):
        parser.error("invalid target SID")
    try:
        raw = json.loads(sys.stdin.buffer.read(4097))
        fields = validate(raw)
    except (ValueError, TypeError):
        print("aos job auth-event: invalid event", file=sys.stderr)
        return 2
    agent = Path(os.environ.get("PI_AGENT", str(Path.home() / ".pi/agent")))
    jobs = agent / "jobs"
    destinations = [(jobs / "streams" / "cauth", None)]
    if args.target_sid:
        destinations.append((args.inbox or jobs / "sessions" / args.target_sid, args.target_sid))
    job = f"{raw['type']}-{raw['session'].replace(':', '-')}-{raw['id']}"
    try:
        for folder, target in destinations:
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            status = folder.absolute() / f"{job}.status.json"
            journal = status.with_name(f"{job}.events.jsonl")
            record = dict(jobId=job, stream="cauth", source="cauth-broker", statusPath=str(status),
                          eventsPath=str(journal), summaryPath=str(status), **fields)
            if target:
                record.update(targetSid=target, status="failed" if raw["type"] in URGENT else "running")
            else:
                record["status"] = "update"  # dashboard only, never a terminal inject
            if not status.exists():
                publish(journal, record)  # one immutable event per job; retry is idempotent
                publish(status, record)
    except OSError:
        print("aos job auth-event: could not publish", file=sys.stderr)
        return 1
    return 0


def status(argv):
    parser = argparse.ArgumentParser(prog="aos job auth-status")
    parser.add_argument("--cauth", default="cauth")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = subprocess.run([args.cauth, "broker", "watch-status"], capture_output=True,
                                text=True, timeout=5, check=True)
        rows = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("cauth status unavailable", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rows))
    else:
        for session, row in sorted(rows.items()):
            print(f"{session:32} {row['state']:13} {row['expires_at'] or '-':27} {row['probe']}")
    return 0
