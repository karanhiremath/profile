"""Run a local non-interactive command and publish its lifecycle to Pi."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import uuid


def publish(path, record):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        try:
            json.dump(record, tmp)
            tmp.write("\n")
            tmp.close()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(prog="aos job run")
    parser.add_argument("--target-sid", default=os.getenv("PI_JOB_BUS_TARGET_SID") or os.getenv("PI_SESSION_ID"))
    parser.add_argument("--inbox", type=Path, help="override the selected coordinator's inbox path")
    parser.add_argument("--summary", type=Path, required=True, help="result artifact path (may not exist yet)")
    parser.add_argument("--label", default="command", help="short, non-secret label")
    parser.add_argument("--case-dir", type=Path, help="prepend trusted decisions.md to a one-shot Pi prompt (last argument)")
    parser.add_argument("--heartbeat", type=int, default=30, metavar="SECONDS")
    argv = sys.argv[1:]
    if not argv or argv[0] != "run":
        parser.error("expected run; use aos job run --help")
    argv = argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command or args.heartbeat < 1:
        parser.error("a command after -- and a positive heartbeat are required")
    sid = args.target_sid
    if not sid or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", sid) or sid in (".", ".."):
        parser.error("a valid coordinator --target-sid or PI_SESSION_ID is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.label):
        parser.error("--label must be a short identifier")
    if args.case_dir is not None:
        if Path(command[0]).name != "pi" or "-p" not in command[1:-1] or command[-1].startswith(("-", "@")):
            parser.error("--case-dir requires pi -p with the task as the last argument")
        try:
            ledger = args.case_dir.resolve(strict=True) / "decisions.md"
            if not ledger.is_file():
                raise ValueError
            with ledger.open("rb") as source:
                raw = source.read(16_385)
            if not raw.strip() or len(raw) > 16_384:
                raise ValueError
            decisions = raw.decode("utf-8")
            if "\x00" in decisions:
                raise ValueError
        except (OSError, ValueError):
            parser.error("case decisions.md must be a nonempty UTF-8 file of at most 16 KiB")
        command[-1] = f"Case decisions (operator-maintained):\n{decisions}\n\nWorker task:\n{command[-1]}"
    agent = Path(os.environ.get("PI_AGENT", str(Path.home() / ".pi/agent")))
    inbox = args.inbox or agent / "jobs" / "sessions" / sid
    job = f"{args.label}-{uuid.uuid4().hex}"
    status = inbox.absolute() / f"{job}.status.json"
    events = status.with_name(f"{job}.events.jsonl")
    record = dict(jobId=job, stream="job-run", source="aos-job", targetSid=sid,
                  statusPath=str(status), eventsPath=str(events), summaryPath=str(args.summary.absolute()))

    def emit(kind, state, **fields):
        event = dict(record, type=kind, status=state, ts=datetime.now(timezone.utc).isoformat(), **fields)
        publish(status, event)
        with os.fdopen(os.open(events, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a") as out:
            out.write(json.dumps(event) + "\n")

    child = None
    pending = None

    def forward(signum, _frame):
        nonlocal pending
        pending = signum
        if child is not None and child.returncode is None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, forward)
    try:
        status.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        emit("job.started", "running")
    except OSError:
        print("aos job: could not register lifecycle; command not launched", file=sys.stderr)
        return 125
    print(f"aos job: {status}", file=sys.stderr)
    try:
        if pending is not None:
            rc = -pending
        else:
            child = subprocess.Popen(command, start_new_session=True)
            if pending is not None:
                forward(pending, None)
            while True:
                try:
                    rc = child.wait(timeout=args.heartbeat)
                    break
                except subprocess.TimeoutExpired:
                    try:
                        emit("job.heartbeat", "running")
                    except OSError:
                        print("aos job: could not publish heartbeat", file=sys.stderr)
    except OSError as exc:
        # Do not echo command arguments or child diagnostics into records.
        rc = 127 if isinstance(exc, FileNotFoundError) else 126
        print(f"aos job: command launch failed (exit {rc})", file=sys.stderr)
    exit_code = rc if rc >= 0 else 128 - rc
    try:
        emit("job.finished" if rc == 0 else "job.failed", "succeeded" if rc == 0 else "failed", exitCode=exit_code)
    except OSError:
        print("aos job: could not publish terminal lifecycle; do not retry without checking the child result", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
