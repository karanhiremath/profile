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
  project_sessions.py pm <project> [--dry-run] [--surface cli|tui] [--provider P] [--model M] [--thinking T]
      Launch or attach the registered PM session (does not switch tmux panes).
  project_sessions.py pl <project> [--dry-run] [--provider P] [--model M] [--thinking T]
  project_sessions.py ensure-pm <project> [--dry-run]
      Provision the registered PM tmux session (hostctl / non-interactive).
  project_sessions.py ensure-pl <project> [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
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


def configured_registry_dirs() -> list[Path]:
    raw = os.environ.get("HERMES_PROJECT_REGISTRY_PATH") or os.environ.get("HERMES_PROJECT_REGISTRY_DIRS")
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()] if raw else list(DEFAULT_REGISTRY_DIRS)


def registry_dirs() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for directory in configured_registry_dirs():
        if not directory.is_dir():
            continue
        key = str(directory.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(directory)
    return out


def profile_dirs() -> list[Path]:
    raw = os.environ.get("HERMES_AGENT_PROFILE_PATH")
    if raw:
        return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
    return [
        Path.home() / "src" / "karan.hiremath" / "agentic" / "hermes" / "profiles",
        Path.home() / "src" / "hermes" / "profiles",
        SCRIPT_DIR / "profiles",
    ]


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-._")
    return slug or "project"


# ---------------------------------------------------------------------------
# Registry YAML hardening: parse repair + legacy schema normalization.
#
# Failure classes handled automatically (backup + atomic rewrite + stderr
# notice + REPAIR_LOG):
#   1. unquoted ': ' inside a plain scalar (yaml: "mapping values are not
#      allowed here") — e.g. `status: REDIRECTED (2026-09-16): "note"`
#   2. tab characters in indentation (yaml: "found character '\\t' ...")
# Anything else fails closed with a precise path/line/column message and a
# remediation hint instead of a raw traceback.
#
# Legacy key shapes (`pm_profile`, `sessions.pm*`, bare `bus:`) are normalized
# in memory only — files on disk are untouched and doctor lists the
# normalizations so registry owners can migrate.
# ---------------------------------------------------------------------------

REGISTRY_AUTOFIX_ENV = "HERMES_REGISTRY_AUTOFIX"
REPAIR_LOG: list[dict[str, str]] = []
NORMALIZATION_LOG: dict[str, list[str]] = {}

_KEY_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[^\s:#][^:]*?):(?P<sep>[ \t]+)(?P<value>\S.*)$")
_BLOCK_STARTERS = set("\"'>&|*[!#{}")


def autofix_enabled() -> bool:
    return str(os.environ.get(REGISTRY_AUTOFIX_ENV, "1")).strip().lower() not in {"0", "false", "no", "off"}


def _yaml_error_location(exc: BaseException) -> tuple[int | None, int | None]:
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        return mark.line + 1, mark.column + 1
    return None, None


def _registry_parse_message(path: Path, exc: BaseException, note: str) -> str:
    line, col = _yaml_error_location(exc)
    where = f"line {line}, column {col}" if line else "unknown location"
    raw = getattr(exc, "problem", None) or getattr(exc, "note", None) or getattr(exc, "context", None) or str(exc)
    text = str(raw).strip()
    problem = text.splitlines()[0] if text else type(exc).__name__
    source_line = ""
    if line:
        try:
            source_line = "\n  > " + str(path.read_text(encoding="utf-8", errors="replace").splitlines()[line - 1])[:200]
        except (OSError, IndexError):
            source_line = ""
    return (
        f"ERROR: registry YAML failed to parse: {path}\n"
        f"  {where}: {problem}{source_line}\n"
        f"  {note}\n"
        "  hint: quote the offending scalar or convert it to a block scalar (key: >-); "
        "keep registry values with ': ' inside them quoted or block-styled"
    )


def _repair_unquoted_colon(text: str, line_no: int) -> str | None:
    """Convert a plain scalar that contains ': ' into a folded block scalar.

    `key: some text: with a colon" -> key: >-\n    key: some text: with a colon"
    Subsequent deeper-indented non-key lines are treated as continuation of the
    same plain scalar. Returns None when the line does not match the known shape.
    """
    lines = text.split("\n")
    idx = line_no - 1
    if idx < 0 or idx >= len(lines):
        return None
    match = _KEY_LINE_RE.match(lines[idx])
    if not match:
        return None
    indent, key, value = match.group("indent"), match.group("key"), match.group("value").rstrip()
    if not value or value[0] in _BLOCK_STARTERS:
        return None
    body_indent = indent.replace("\t", "  ") + "  "
    cont: list[str] = []
    j = idx + 1
    while j < len(lines):
        nxt = lines[j]
        if not nxt.strip():
            break
        nxt_indent = len(nxt) - len(nxt.lstrip(" "))
        if nxt_indent <= len(indent.replace("\t", "  ")):
            break
        if _KEY_LINE_RE.match(nxt):
            break
        cont.append(nxt)
        j += 1
    block = [f"{indent}{key}: >-", body_indent + value]
    for line in cont:
        cont_indent = len(line) - len(line.lstrip(" "))
        block.append(line if cont_indent >= len(body_indent) else body_indent + line.lstrip())
    return "\n".join(lines[:idx] + block + lines[idx + 1 + len(cont):])


def _repair_tab_indentation(text: str) -> str:
    """Expand leading-tab indentation to two spaces per tab (YAML forbids tab indentation)."""
    out: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip(" \t")
        lead = line[: len(line) - len(stripped)]
        out.append(lead.replace("\t", "  ") + stripped if "\t" in lead else line)
    return "\n".join(out)


def _repair_registry_text(path: Path, text: str, original: str, exc: yaml.YAMLError) -> str:
    """Attempt known repairs; persist the first parseable result. Raises SystemExit otherwise."""
    if not autofix_enabled():
        raise SystemExit(_registry_parse_message(path, exc, "registry autofix is disabled (set HERMES_REGISTRY_AUTOFIX=1 to enable)"))
    attempted: list[str] = []
    for _ in range(4):
        line, _col = _yaml_error_location(exc)
        problem = str(getattr(exc, "problem", None) or "")
        candidate: str | None = None
        repair_kind = ""
        if "mapping values are not allowed here" in problem and line:
            repair_kind = "quoted-colon plain scalar -> folded block scalar"
            candidate = _repair_unquoted_colon(text, line)
        elif "found character" in problem and "\\t" in problem:
            repair_kind = "tab indentation -> spaces"
            candidate = _repair_tab_indentation(text)
        if candidate is None or candidate == text:
            break
        try:
            yaml.safe_load(candidate)
        except (yaml.YAMLError, UnicodeDecodeError) as next_exc:
            text, exc = candidate, next_exc
            continue
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.repair-bak-{stamp}")
        try:
            backup.write_text(original, encoding="utf-8")
            tmp = path.with_name(f".{path.name}.repair-tmp")
            tmp.write_text(candidate, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as write_exc:
            raise SystemExit(f"ERROR: repaired registry text for {path} but could not write it: {write_exc}") from write_exc
        notice = f"registry-autofix: repaired {path}: {repair_kind}; backup: {backup}"
        print(notice, file=sys.stderr)
        REPAIR_LOG.append({"path": str(path), "repair": repair_kind, "backup": str(backup)})
        return candidate
    raise SystemExit(_registry_parse_message(path, exc, "autofix: no known repair applied"))


def normalize_registry_shape(data: dict[str, Any], path: Path) -> dict[str, Any]:
    """Map legacy registry key shapes onto the canonical schema, in memory only.

    Legacy shapes (pre-2026-09 registries):
      pm_profile: x            -> pm.profile
      sessions: {pm_session: s, pl_session: p} / {pm: s, pl: p} -> tmux.{pm_session,pl_session}
      bus: <repo-relative>     -> event_bus.publish_paths + default event_types
    Relative legacy bus paths are anchored at the registry file's repo root.
    """
    notes: list[str] = []
    if data.get("pm_profile") and not (data.get("pm") or {}).get("profile"):
        pm = data.get("pm")
        if not isinstance(pm, dict):
            pm = data["pm"] = {}
        pm["profile"] = str(data["pm_profile"])
        notes.append("pm_profile -> pm.profile")
    tmux = data.get("tmux") if isinstance(data.get("tmux"), dict) else None
    sessions = data.get("sessions") if isinstance(data.get("sessions"), dict) else None
    if sessions:
        for legacy, canonical in (("pm_session", "pm_session"), ("pl_session", "pl_session"),
                                  ("implementation_session", "implementation_session"),
                                  ("pm", "pm_session"), ("pl", "pl_session")):
            if legacy in sessions and not (tmux or {}).get(canonical):
                if tmux is None:
                    tmux = data["tmux"] = {}
                tmux[canonical] = str(sessions[legacy])
                notes.append(f"sessions.{legacy} -> tmux.{canonical}")
    if "bus" in data and not isinstance(data.get("event_bus"), dict):
        raw = str(data["bus"]).strip()
        if raw:
            resolved = Path(raw).expanduser()
            if not resolved.is_absolute():
                resolved = _repo_root_for(path) / resolved
            data["event_bus"] = {
                "publish_paths": [{"path": str(resolved)}],
                "event_types": ["pm_started", "pm_attached", "project_lead_started",
                                "project_lead_attached", "pm_action_required"],
            }
            notes.append("bus -> event_bus.publish_paths (+default event_types incl pm_action_required)")
    if notes:
        data["_normalizations"] = notes
        key = str(path)
        if key not in NORMALIZATION_LOG:
            NORMALIZATION_LOG[key] = notes
    return data


def _repo_root_for(path: Path) -> Path:
    directory = path.parent
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return directory


def load_registry(path: Path) -> dict[str, Any]:
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"ERROR: cannot read registry {path}: {exc}") from exc
    text = original
    while True:
        try:
            data = yaml.safe_load(text) or {}
            break
        except yaml.YAMLError as exc:
            if not autofix_enabled():
                raise SystemExit(_registry_parse_message(path, exc, "registry autofix is disabled (set HERMES_REGISTRY_AUTOFIX=1 to enable)")) from exc
            text = _repair_registry_text(path, text, original, exc)
        except UnicodeDecodeError as exc:
            raise SystemExit(_registry_parse_message(path, exc, "registry is not valid UTF-8; re-save it as UTF-8")) from exc
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: registry is not a mapping: {path}")
    data = normalize_registry_shape(data, path)
    data.setdefault("name", path.stem)
    data["_path"] = str(path)
    return data


def is_agent_profile(data: dict[str, Any]) -> bool:
    """Identify co-located agent profiles without hiding malformed projects."""
    profile_keys = {"llm", "persona", "toolsets", "surface", "platform"}
    project_keys = {"pm", "tmux", "sessions", "event_bus", "workdir", "goal"}
    return bool(profile_keys.intersection(data)) and not bool(project_keys.intersection(data))


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
            if is_agent_profile(data):
                continue
            aliases = data.get("aliases") or []
            if data.get("name") == name or name in aliases:
                return data
    searched = "\n  ".join(str(d) for d in configured_registry_dirs()) or "(no registry dirs configured)"
    raise SystemExit(f"ERROR: no such Hermes project: {name}. Searched:\n  {searched}")


def project_list(errors: list[str] | None = None) -> list[dict[str, str]]:
    if not registry_dirs():
        configured = "\n  ".join(str(path) for path in configured_registry_dirs())
        raise SystemExit(
            "ERROR: no Hermes project registry directory is available. Checked:\n  "
            f"{configured}\nSet HERMES_PROJECT_REGISTRY_PATH or install/sync the work registry."
        )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for directory in registry_dirs():
        for path in sorted(directory.glob("*.y*ml")):
            try:
                data = load_registry(path)
            except SystemExit as exc:
                if errors is not None:
                    errors.append(str(exc).strip())
                    continue
                raise
            if is_agent_profile(data):
                continue
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
    if isinstance(value, dict):
        value = value.get("tmux_session") or value.get("session")
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


def pm_launch_command(project: dict[str, Any], surface: str = "tui") -> str:
    pm = project.get("pm") or {}
    if pm.get("command") and surface == "tui":
        return str(pm["command"])
    profile = pm.get("profile") or project.get("pm_profile")
    if not profile:
        raise SystemExit(f"ERROR: project {project.get('name')} has no pm.profile or pm.command")
    cmd = [agents_bin(), "up", str(profile), "--surface", surface]
    if surface == "cli":
        cmd.extend(["--", "--continue", "--cli"])
    return " ".join(shlex.quote(part) for part in cmd)


def tmux_exists(session: str) -> bool:
    if not shutil.which("tmux"):
        raise SystemExit("ERROR: tmux is unavailable on PATH; install tmux before starting Hermes PM sessions")
    proc = subprocess.run(["tmux", "has-session", "-t", session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.returncode == 0


def writable_event_paths(project: dict[str, Any]) -> list[Path]:
    paths = publish_paths(project)
    seen: set[str] = set()
    result = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def validate_project(project: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = str(project.get("name") or "")
    if not name:
        errors.append("name is required")
    pm = project.get("pm") or {}
    if not isinstance(pm, dict) or not (pm.get("profile") or pm.get("command") or project.get("pm_profile")):
        errors.append("pm.profile or pm.command is required")
    tmux = project.get("tmux") or {}
    if not isinstance(tmux, dict) or not tmux.get("pm_session"):
        errors.append("tmux.pm_session is required")
    else:
        for key in ("pm_session", "pl_session", "implementation_session"):
            value = str(tmux.get(key) or "")
            if value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                errors.append(f"tmux.{key} contains unsupported characters: {value!r}")
    cwd = workdir(project)
    if not cwd.is_dir():
        errors.append(f"workdir does not exist or is not a directory: {cwd}")
    bus = project.get("event_bus")
    if not isinstance(bus, dict):
        errors.append("event_bus must be a mapping with event_types and a writable source or publish path")
    else:
        raw_types = bus.get("event_types") or []
        if isinstance(raw_types, list):
            event_types = {str(value) for value in raw_types}
        else:
            errors.append("event_bus.event_types must be a list")
            event_types = set()
        if "pm_action_required" not in event_types:
            errors.append("event_bus.event_types must include pm_action_required")
        if not writable_event_paths(project):
            errors.append("event_bus needs at least one writable source or publish path")
    profile = pm.get("profile") if isinstance(pm, dict) else None
    profile = profile or project.get("pm_profile")
    if profile and not any((directory / f"{profile}.yaml").is_file() for directory in profile_dirs()):
        errors.append(f"PM profile is unavailable on HERMES_AGENT_PROFILE_PATH: {profile}")
    return errors


def doctor() -> tuple[dict[str, Any], bool]:
    configured = configured_registry_dirs()
    available = registry_dirs()
    errors: list[str] = []
    warnings: list[str] = []
    load_errors: list[str] = []
    if not available:
        errors.append(
            "no registry directory is available; set HERMES_PROJECT_REGISTRY_PATH or sync the registered project repo"
        )
    if not shutil.which("tmux"):
        errors.append("tmux is unavailable on PATH")
    agents = Path(agents_bin())
    if not agents.is_file() or not os.access(agents, os.X_OK):
        errors.append(f"Hermes agents launcher is missing or not executable: {agents}")
    projects: list[dict[str, Any]] = []
    if available:
        for row in project_list(errors=load_errors):
            try:
                project = find_project(row["name"])
            except SystemExit as exc:
                load_errors.append(str(exc).strip())
                continue
            project_errors = validate_project(project)
            projects.append({
                **row,
                "valid": not project_errors,
                "errors": project_errors,
                "normalizations": list(project.get("_normalizations") or []),
            })
            warnings.extend(f"project {row['name']}: {error}" for error in project_errors)
        if not projects and not load_errors:
            errors.append("registry directories contain no project YAML files")
    errors.extend(load_errors)
    result = {
        "ok": not errors,
        "autofix": autofix_enabled(),
        "repairs": [dict(entry) for entry in REPAIR_LOG],
        "normalization_count": sum(len(notes) for notes in NORMALIZATION_LOG.values()),
        "configured_registry_dirs": [str(path) for path in configured],
        "registry_dirs": [str(path) for path in available],
        "project_count": len(projects),
        "projects": projects,
        "commands": {"tmux": shutil.which("tmux"), "agents": str(agents)},
        "errors": errors,
        "warnings": warnings,
        "remediation": (
            "Set HERMES_PROJECT_REGISTRY_PATH to readable registry directories, ensure each live project has a PM "
            "profile/session/event bus, install tmux, then run `cosw --dispatch-doctor`. Stale project workdirs are "
            "warnings and do not block COSW launch; hostctl/ensure-pm stay fail-closed for those projects."
        ),
    }
    return result, not errors


def publish_paths(project: dict[str, Any]) -> list[Path]:
    bus = project.get("event_bus") or {}
    if not isinstance(bus, dict):
        return []
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


def live_tui_target(profile: str, session: str) -> str | None:
    try:
        import alias_seat
    except ImportError:
        return None
    return alias_seat.attach_target(profile, session)


def ensure_pm(project: dict[str, Any], dry_run: bool, surface: str = "tui") -> tuple[str, bool]:
    session = session_name(project, "pm")
    created = False
    pm = project.get("pm") or {}
    profile = str(pm.get("profile") or project.get("pm_profile") or "")
    if surface == "tui" and profile:
        target = live_tui_target(profile, session)
        if target:
            emit_project_event(
                project,
                "pm_attached",
                f"pm_attached manifest event: live TUI holds {profile}; attaching {target}.",
                session,
                dry_run,
            )
            return session, False
    if not tmux_exists(session):
        launch = pm_launch_command(project, surface=surface)
        cwd = workdir(project)
        new_cmd = ["tmux", "new-session", "-d", "-s", session, "-c", str(cwd), launch]
        if dry_run:
            print(" ".join(shlex.quote(c) for c in new_cmd))
        else:
            if not cwd.is_dir():
                raise SystemExit(
                    f"ERROR: registered project workdir does not exist: {cwd}. "
                    "Fix the project registry or create the intended isolated worktree first."
                )
            subprocess.check_call(new_cmd)
            created = True
    kind = "pm_started" if created else "pm_attached"
    emit_project_event(
        project,
        kind,
        f"{kind} manifest event: PM session ensured for project {project.get('name')} at {session}.",
        session,
        dry_run,
    )
    return session, created


def ensure_pl(project: dict[str, Any], dry_run: bool) -> tuple[str, bool]:
    session = session_name(project, "pl")
    created = False
    if not tmux_exists(session):
        cwd = workdir(project)
        new_cmd = ["tmux", "new-session", "-d", "-s", session, "-c", str(cwd)]
        if dry_run:
            print(" ".join(shlex.quote(c) for c in new_cmd))
        else:
            if not cwd.is_dir():
                raise SystemExit(
                    f"ERROR: registered project workdir does not exist: {cwd}. "
                    "Fix the project registry or create the intended isolated worktree first."
                )
            subprocess.check_call(new_cmd)
            created = True
    kind = "project_lead_started" if created else "project_lead_attached"
    emit_project_event(
        project,
        kind,
        f"{kind} manifest event: PL implementation session ensured for project {project.get('name')} at {session}.",
        session,
        dry_run,
    )
    return session, created


def cmd_ensure(project_name: str, kind: str, dry_run: bool) -> int:
    project = find_project(project_name)
    session, created = ensure_pm(project, dry_run) if kind == "pm" else ensure_pl(project, dry_run)
    print(json.dumps({"project": project.get("name"), "kind": kind, "session": session, "created": created}))
    return 0

def cmd_pm(project_name: str, dry_run: bool, surface: str = "tui") -> int:
    """Launch or attach the registered PM session for a project.

    Attaches a live TUI when one already holds the PM profile; otherwise
    provisions the registered tmux session (ensure semantics) and attaches it.
    Interactive ``pm`` attaches the current pane via tmux when outside tmux.
    """
    project = find_project(project_name)
    session = session_name(project, "pm")
    pm = project.get("pm") or {}
    profile = str(pm.get("profile") or project.get("pm_profile") or "")
    if surface == "tui" and profile:
        target = live_tui_target(profile, session)
        if target:
            emit_project_event(
                project,
                "pm_attached",
                f"pm_attached manifest event: live TUI holds {profile}; attaching {target}.",
                session,
                dry_run,
            )
            return attach_or_switch(target, dry_run)
    ensure_pm(project, dry_run, surface=surface)
    return attach_or_switch(session, dry_run)


def cmd_pl(project_name: str, dry_run: bool) -> int:
    project = find_project(project_name)
    session = session_name(project, "pl")
    if not tmux_exists(session):
        raise SystemExit(
            f"ERROR: project lead session is not running: {session}. "
            "Use `ensure-pl <project>` or ask the PM to register/spawn a project lead first."
        )
    emit_project_event(
        project,
        "project_lead_attached",
        f"project_lead_attached manifest event: pl command routed project {project.get('name')} to tmux session {session}.",
        session,
        dry_run,
    )
    return attach_or_switch(session, dry_run)


# Providers whose "provider/model" prefixes split into explicit provider +
# model when set via --model at launch time. Mirrors llm-flags.sh in bash.
LLM_KNOWN_PROVIDERS = {
    "openai-codex", "openai", "anthropic", "anthropic-beta", "azure-openai-responses",
    "amazon-bedrock", "cursor", "together", "xai", "xai-oauth", "openrouter", "pi",
    "nemoclaw", "ollama", "moa", "google", "google-vertex", "moonshotai", "groq",
    "cerebras", "zai", "mistral", "deepseek",
}


def split_model_selector(value: str) -> tuple[str, str]:
    """provider/model -> (provider, model) when the prefix is a known provider."""
    if "/" in value:
        head, rest = value.split("/", 1)
        if head in LLM_KNOWN_PROVIDERS and rest:
            return head, rest
    return "", value


def apply_llm_flags(args: argparse.Namespace) -> None:
    """Export launcher env overrides from --provider/--model/--thinking flags.

    pm execs the registered launch command, so the env propagates into the
    spawned herm/hermes process. pl attaches an existing tmux session where
    model flags are meaningless — accepted but ignored with a warning.
    """
    provider = getattr(args, "llm_provider", None) or ""
    model = getattr(args, "llm_model", None) or ""
    thinking = getattr(args, "llm_thinking", None) or ""
    if model:
        split_provider, split_model = split_model_selector(model)
        if split_provider:
            if provider and provider != split_provider:
                raise SystemExit(f"ERROR: conflicting --provider {provider} vs --model {model}")
            provider = provider or split_provider
            model = split_model
    overrides = {
        "HERMES_AGENT_LLM_PROVIDER": provider,
        "HERMES_INFERENCE_PROVIDER": provider,
        "HERMES_TUI_PROVIDER": provider,
        "HERMES_AGENT_LLM_MODEL": model,
        "HERMES_INFERENCE_MODEL": model,
        "HERMES_MODEL": model,
        "HERMES_AGENT_LLM_THINKING": thinking,
    }
    if args.cmd == "pl" and (provider or model or thinking):
        print(
            "pl: attaches an existing session; --provider/--model/--thinking ignored "
            "(model is session state; use pm or ensure-pm to launch with an override)",
            file=sys.stderr,
        )
        return
    for key, value in overrides.items():
        if value:
            os.environ[key] = value


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("names")
    d = sub.add_parser("doctor")
    d.add_argument("--no-autofix", action="store_true", help="report registry defects without repairing them")
    r = sub.add_parser("resolve")
    r.add_argument("project")
    for name in ("pm", "pl", "ensure-pm", "ensure-pl"):
        p = sub.add_parser(name)
        p.add_argument("project")
        p.add_argument("--dry-run", action="store_true")
        if name == "pm":
            p.add_argument("--surface", choices=("cli", "tui"), default="tui")
        p.add_argument("--provider", dest="llm_provider", default="", help="launch-scoped provider (openai-codex, cursor, together, xai, ...)")
        p.add_argument("--model", dest="llm_model", default="", help="launch-scoped model; provider/ prefix splits when known")
        p.add_argument("--thinking", dest="llm_thinking", default="", help="launch-scoped thinking level (low, medium, high, xhigh)")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(json.dumps(project_list(), indent=2))
        return 0
    if args.cmd == "names":
        for row in project_list():
            print(row["name"])
        return 0
    if args.cmd == "doctor":
        if getattr(args, "no_autofix", False):
            os.environ[REGISTRY_AUTOFIX_ENV] = "0"
        result, ok = doctor()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if ok else 1
    if args.cmd == "resolve":
        print(json.dumps(find_project(args.project), indent=2, sort_keys=True))
        return 0
    if args.cmd == "pm":
        apply_llm_flags(args)
        return cmd_pm(args.project, args.dry_run, surface=args.surface)
    if args.cmd == "pl":
        apply_llm_flags(args)
        return cmd_pl(args.project, args.dry_run)
    if args.cmd == "ensure-pm":
        return cmd_ensure(args.project, "pm", args.dry_run)
    if args.cmd == "ensure-pl":
        return cmd_ensure(args.project, "pl", args.dry_run)
    raise SystemExit(f"ERROR: unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
