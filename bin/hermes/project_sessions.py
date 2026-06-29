#!/usr/bin/env python3
"""Resolve Hermes project sessions and attach PM/PL tmux consoles.

Registry files are YAML and live on a search path:

- $HERMES_PROJECT_REGISTRY_PATH or $HERMES_PROJECT_REGISTRY_DIRS, os.pathsep-separated
- ~/src/karan.hiremath/agentic/hermes/projects
- ~/src/hermes/projects
- ~/src/profile/bin/hermes/projects

Commands:
  project_sessions.py list
  project_sessions.py names
  project_sessions.py resolve <project>
  project_sessions.py pm <project> [--dry-run]
  project_sessions.py pl <project> [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY_DIRS = [
    Path.home() / "src" / "karan.hiremath" / "agentic" / "hermes" / "projects",
    Path.home() / "src" / "hermes" / "projects",
    SCRIPT_DIR / "projects",
]


def registry_dirs() -> list[Path]:
    raw = os.environ.get("HERMES_PROJECT_REGISTRY_PATH") or os.environ.get("HERMES_PROJECT_REGISTRY_DIRS")
    dirs = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()] if raw else DEFAULT_REGISTRY_DIRS
    out: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        if not directory.exists():
            continue
        key = str(directory.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(directory)
    return out


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-._")
    return slug or "project"


def load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: registry is not a mapping: {path}")
    data.setdefault("name", path.stem)
    data["_path"] = str(path)
    return data


def find_project(name: str) -> dict[str, Any]:
    candidates = [name, slugify(name)]
    for directory in registry_dirs():
        for candidate in candidates:
            for suffix in (".yaml", ".yml"):
                path = directory / f"{candidate}{suffix}"
                if path.exists():
                    return load_registry(path)
        for path in sorted(directory.glob("*.y*ml")):
            data = load_registry(path)
            aliases = data.get("aliases") or []
            if data.get("name") == name or name in aliases:
                return data
    searched = "\n  ".join(str(d) for d in registry_dirs()) or "(no registry dirs found)"
    raise SystemExit(f"ERROR: no such Hermes project: {name}. Searched:\n  {searched}")


def project_list() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for directory in registry_dirs():
        for path in sorted(directory.glob("*.y*ml")):
            data = load_registry(path)
            name = str(data.get("name") or path.stem)
            if name in seen:
                continue
            seen.add(name)
            rows.append({
                "name": name,
                "description": str(data.get("description") or ""),
                "source": str(path),
                "pm_session": session_name(data, "pm"),
                "pl_session": session_name(data, "pl", required=False) or "",
            })
    return rows


def session_name(project: dict[str, Any], kind: str, *, required: bool = True) -> str:
    tmux = project.get("tmux") or {}
    sessions = project.get("sessions") or {}
    value = tmux.get(f"{kind}_session") or sessions.get(kind)
    if value:
        return str(value)
    if kind == "pm":
        return f"pm-{slugify(str(project.get('name')))}"
    if required:
        raise SystemExit(
            f"ERROR: project {project.get('name')} has no registered {kind.upper()} tmux session. "
            "Ask the CoS/PM to register one in the project registry."
        )
    return ""


def workdir(project: dict[str, Any]) -> Path:
    tmux = project.get("tmux") or {}
    value = tmux.get("workdir") or project.get("workdir") or str(Path.home())
    return Path(str(value)).expanduser()


def agents_bin() -> str:
    override = os.environ.get("HERMES_AGENTS_BIN")
    if override:
        return override
    return str(SCRIPT_DIR / "agents")


def pm_launch_command(project: dict[str, Any]) -> str:
    pm = project.get("pm") or {}
    if pm.get("command"):
        return str(pm["command"])
    profile = pm.get("profile") or project.get("pm_profile")
    if not profile:
        raise SystemExit(f"ERROR: project {project.get('name')} has no pm.profile or pm.command")
    return " ".join([shlex.quote(agents_bin()), "up", shlex.quote(str(profile)), "--surface", "tui"])


def tmux_exists(session: str) -> bool:
    proc = subprocess.run(["tmux", "has-session", "-t", session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.returncode == 0


def publish_paths(project: dict[str, Any]) -> list[Path]:
    bus = project.get("event_bus") or {}
    paths: list[Path] = []
    for item in bus.get("publish_paths") or []:
        if isinstance(item, dict):
            value = item.get("path")
        else:
            value = item
        if value:
            paths.append(Path(str(value)).expanduser())
    if not paths:
        for item in bus.get("sources") or []:
            if isinstance(item, dict) and item.get("writable", True) and item.get("path"):
                paths.append(Path(str(item["path"])).expanduser())
    return paths


def emit_project_event(project: dict[str, Any], kind: str, content: str, session: str, dry_run: bool) -> None:
    if dry_run:
        return
    event = {
        "agent_id": "hermes-project-session",
        "kind": kind,
        "severity": "info",
        "project": project.get("name"),
        "session": session,
        "message": {"role": "system", "content": content},
        "registry_path": project.get("_path"),
        "timestamp": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    for path in publish_paths(project):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, separators=(",", ":")) + "\n")


def attach_or_switch(session: str, dry_run: bool) -> int:
    cmd = ["tmux", "switch-client", "-t", session] if os.environ.get("TMUX") else ["tmux", "attach-session", "-t", session]
    if dry_run:
        print(" ".join(shlex.quote(c) for c in cmd))
        return 0
    return subprocess.call(cmd)


def cmd_pm(project_name: str, dry_run: bool) -> int:
    project = find_project(project_name)
    session = session_name(project, "pm")
    created = False
    if not tmux_exists(session):
        launch = pm_launch_command(project)
        cwd = workdir(project)
        new_cmd = ["tmux", "new-session", "-d", "-s", session, "-c", str(cwd), launch]
        if dry_run:
            print(" ".join(shlex.quote(c) for c in new_cmd))
        else:
            cwd.mkdir(parents=True, exist_ok=True)
            subprocess.check_call(new_cmd)
            created = True
    kind = "pm_started" if created else "pm_attached"
    emit_project_event(
        project,
        kind,
        f"{kind} manifest event: pm command routed project {project.get('name')} to tmux session {session}.",
        session,
        dry_run,
    )
    return attach_or_switch(session, dry_run)


def cmd_pl(project_name: str, dry_run: bool) -> int:
    project = find_project(project_name)
    session = session_name(project, "pl")
    if not tmux_exists(session):
        raise SystemExit(
            f"ERROR: project lead session is not running: {session}. "
            "Use `pm <project>` or ask the PM to register/spawn a project lead first."
        )
    emit_project_event(
        project,
        "project_lead_attached",
        f"project_lead_attached manifest event: pl command routed project {project.get('name')} to tmux session {session}.",
        session,
        dry_run,
    )
    return attach_or_switch(session, dry_run)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("names")
    r = sub.add_parser("resolve")
    r.add_argument("project")
    for name in ("pm", "pl"):
        p = sub.add_parser(name)
        p.add_argument("project")
        p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(json.dumps(project_list(), indent=2))
        return 0
    if args.cmd == "names":
        for row in project_list():
            print(row["name"])
        return 0
    if args.cmd == "resolve":
        print(json.dumps(find_project(args.project), indent=2, sort_keys=True))
        return 0
    if args.cmd == "pm":
        return cmd_pm(args.project, args.dry_run)
    if args.cmd == "pl":
        return cmd_pl(args.project, args.dry_run)
    raise SystemExit(f"ERROR: unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
