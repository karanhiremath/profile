"""Drain a trusted candidate-ready job-bus inbox once and record Forge submissions."""

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
IMAGE = re.compile(r"([a-z0-9][a-z0-9.-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)+)@(sha256:[a-f0-9]{64})")
EVENT_FILE = re.compile(r"(candidate-ready-[a-f0-9]{64})\.status\.json")
ROUTE = ("infra", "model", "cluster", "release", "component")


class DispatchError(Exception):
    pass


class PermissionDenied(DispatchError):
    pass


def require(condition, reason="invalid candidate-ready input or local state"):
    if not condition:
        raise DispatchError(reason)


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode))
        return read_json(stream, 256 * 1024)


def read_json(stream, limit):
    raw = stream.read(limit + 1)
    require(len(raw) <= limit)
    value = json.loads(raw)
    require(isinstance(value, dict))
    return value


def atomic(path, document):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".validate-ready-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(document, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def name(value):
    require(isinstance(value, str) and NAME.fullmatch(value))
    return value


def routes(path):
    data = read(path)
    require(data["schema"] == "aos.validate-on-ready.routes.v1")
    mapping = {}
    for entry in data["routes"]:
        key = tuple(name(entry[field]) for field in ROUTE)
        require(key not in mapping and entry["mode"] == "attach-to-existing-release")
        repository = entry["repository"]
        require(IMAGE.fullmatch(repository + "@sha256:" + "0" * 64))
        mapping[key] = repository, name(entry["config_ref"])
    return mapping


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Forge:
    def __init__(self, origin, token):
        parsed = urlsplit(origin)
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username
                and not parsed.password and parsed.path in ("", "/") and not parsed.query
                and not parsed.fragment and not any(c.isspace() for c in origin),
                "Forge origin must be a bare HTTPS origin")
        require(token, "FORGE_API_KEY must be injected via the approved credential path")
        self.origin = origin.rstrip("/")
        self.token = token
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path="", body=None):
        request = Request(self.origin + "/v1/validations" + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"X-API-Key": self.token, "X-Forge-Actor": "cbuild",
                                   "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, read_json(response, 1024 * 1024)
        except HTTPError as error:
            code = error.code
            error.close()
            # Never log provider error bodies or follow redirects.
            if code == 409 and body is not None:
                return code, {}
            failure = PermissionDenied if code in (401, 403) else DispatchError
            raise failure(f"Forge {request.get_method()} {request.selector} returned HTTP {code}; "
                          "inspect claim before retry") from None


def observe(path, sid, mapping, state, forge, case_dir):
    event = read(path)
    job = EVENT_FILE.fullmatch(path.name)[1]
    require(all(event.get(field) == value for field, value in {
        "schema": "pi.job-watcher.v1", "jobId": job, "source": "cbuild", "targetSid": sid,
        "stream": "candidate-ready", "type": "job.finished", "status": "succeeded",
        "eventType": "candidate-ready",
    }.items()))
    candidate = event["candidate"]
    route = tuple(name(candidate[field]) for field in ROUTE)
    name(candidate["rollout"])
    image = candidate["image"]
    match = IMAGE.fullmatch(image)
    require(match)
    repository, digest = match.groups()
    observed = datetime.fromisoformat(event["ts"])
    now = datetime.now(timezone.utc)
    require(observed.tzinfo is not None and observed <= now)
    if route not in mapping or repository != mapping[route][0]:
        if now - observed > timedelta(minutes=5):
            return None
        raise DispatchError("no approved Forge route for the candidate")
    config = mapping[route][1]
    key = "cbuild-ready-" + digest.removeprefix("sha256:")
    workflow_id = "id_" + key
    claim_path = state / f"{key}.json"
    fd = os.open(state / f"{key}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "rb+") as lock:
        require(stat.S_ISREG(os.fstat(lock.fileno()).st_mode))
        fcntl.flock(lock, fcntl.LOCK_EX)
        context = dict(zip(ROUTE, route), origin=forge.origin, image=image, config_ref=config)
        try:
            claim = read(claim_path)
        except FileNotFoundError:
            if datetime.now(timezone.utc) - observed > timedelta(minutes=5):
                return None
            # Commit intent BEFORE the side effect. Never POST this digest again from
            # this ledger, even if a failed Forge execution could reuse the ID.
            claim = {"context": context, "event": job, "observed_at": event["ts"]}
            atomic(claim_path, claim)
            status, response = forge.request(body={"config_ref": config,
                                                  "overrides": {"candidate": {"image": image}},
                                                  "trigger": {"source": "workflow"},
                                                  "idempotency_key": key})
            if status == 202:
                require(response.get("id") == workflow_id and response.get("workflow_id") == workflow_id
                        and response.get("idempotency_key") == key and response.get("status") == "pending",
                        "unexpected Forge acceptance; claim retained for reconciliation")
                claim["receipt"] = receipt(claim, workflow_id, digest, "accepted")
                atomic(claim_path, claim)
            else:
                require(status == 409, "unexpected Forge status; claim retained for reconciliation")
        require(claim["context"] == context, "digest already claimed for a different Forge context")
        if "receipt" not in claim:
            status, run = forge.request("/" + workflow_id)
            effective = run.get("effective_config") or {}
            require(status == 200 and run.get("id") == workflow_id and run.get("config_ref") == config
                    and (run.get("trigger") or {}).get("actor") == "cbuild"
                    and (effective.get("candidate") or {}).get("image") == image,
                    "Forge readback has not confirmed config, actor and digest; claim retained")
            claim["receipt"] = receipt(claim, workflow_id, digest, "reconciled")
            atomic(claim_path, claim)
        path = case_dir / f"{key}.json"
        atomic(path, claim["receipt"])
        return path


def receipt(claim, workflow_id, digest, state):
    return {"schema": "aos.forge-validation-submission.v1", "validation_id": workflow_id,
            "workflow_id": workflow_id, "candidate_digest": digest,
            "config_ref": claim["context"]["config_ref"], "status": state,
            "candidate": {field: claim["context"][field] for field in (*ROUTE, "image")},
            "event_id": claim["event"], "ready_at": claim["observed_at"],
            "observed_at": datetime.now(timezone.utc).isoformat()}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aos validate-on-ready", description=__doc__)
    parser.add_argument("--target-sid", required=True)
    parser.add_argument("--forge-origin", required=True)
    for flag in ("inbox", "routes", "state-dir", "case-dir", "receipt-importer", "temporal-jobs-dir"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        name(args.target_sid)
        mapping = routes(args.routes)
        require(args.receipt_importer.is_file(), "cai-aos receipt importer missing")
        forge = Forge(args.forge_origin, os.environ.get("FORGE_API_KEY"))
        case_dir = args.case_dir.resolve(strict=True) / "forge-validation-receipts"
        for directory in (args.state_dir, case_dir):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(args.inbox.is_dir(), "job-bus inbox missing")
        failed = False
        for path in sorted(args.inbox.iterdir()):
            if not EVENT_FILE.fullmatch(path.name):
                continue
            try:
                result = observe(path, args.target_sid, mapping, args.state_dir, forge, case_dir)
                if result:
                    # The importer is a trusted local tool, not a command from the bus.
                    env = {key: value for key, value in os.environ.items() if key != "FORGE_API_KEY"}
                    subprocess.run([sys.executable, str(args.receipt_importer), "forge-validation",
                                    str(result), "--jobs-dir", str(args.temporal_jobs_dir)], env=env,
                                   check=True, timeout=15, stdout=subprocess.DEVNULL)
                    print(result.name)
            except (PermissionDenied, PermissionError):
                raise
            except DispatchError as error:
                print(f"aos validate-on-ready: {path.name}: {error}", file=sys.stderr)
                failed = True
            except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
                print(f"aos validate-on-ready: {path.name}: input, Forge exchange or receipt failed",
                      file=sys.stderr)
                failed = True
        return 2 if failed else 0
    except DispatchError as error:
        print(f"aos validate-on-ready: {error}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        print("aos validate-on-ready: invalid input, unavailable output or failed Forge exchange; inspect claims",
              file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
