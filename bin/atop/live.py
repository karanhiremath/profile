#!/usr/bin/env python3
"""atop.live.v1 — live sessions + AOS layer health. stdout JSON or markdown."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA = "atop.live.v1"

LAYER_SKILLS = (
    ("a-top", "aos", ("a-top",)),
    ("aos", "aos", ("aos",)),
    ("aop", "aop", ("aop",)),
    ("attach", "aop", ("attach",)),
    ("handoff", "aop", ("handoff",)),
    ("session-compaction", "aop", ("session-compaction",)),
    ("infra-herm", "infra", ("infra-herm",)),
    ("infra-host", "infra", ("infra-host",)),
    ("atop-vi", "surface", ("atop-vi",)),
)

HARNESS_HOMES = (
    ("pi-home", Path(".pi/agent/skills")),
    ("codex-home", Path(".codex/skills")),
    ("hermes-cos", Path(".local/share/hermes-agents/chief-of-staff/skills")),
    ("hermes-cosw", Path(".local/share/hermes-agents/chief-of-staff-work/skills")),
    ("hermes-default", Path(".hermes/skills")),
)

REDACT = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|Bearer\s+\S+)"
)
IDLE_HINTS = (
    "waiting",
    "@steer",
    "ready",
    "press enter",
    "❯",
    "% ",
    "$ ",
    "π ",
)
BUSY_HINTS = (
    "thinking",
    "compacting",
    "tool:",
    "running tool",
    "called ",
)
CHROME = (
    "cursor:local",
    "fast:on lanes",
    "job-bus unscoped",
    "-- insert --",
    "auto mode on",
)


def home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def host_class(h: Path | None = None) -> str:
    h = h or home()
    hn = os.uname().nodename.split(".")[0].lower()
    if os.uname().sysname == "Darwin" and not (h / "src/karan.hiremath").is_dir():
        return "personal"
    if hn in {"khire-mac-mini", "home-mac-mini"}:
        return "personal"
    if (h / "src/karan.hiremath").is_dir():
        return "work"
    return "personal"


def _run(argv: list[str], timeout: float = 4.0) -> str:
    try:
        out = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout or ""


def redact(text: str) -> str:
    return REDACT.sub("[redacted]", text)


def classify_cmd(cmd: str, title: str = "") -> str | None:
    blob = f"{cmd} {title}".lower()
    if any(
        x in blob
        for x in (
            "cursor-sdk-bridge",
            "bg-pty-host",
            "job-runner",
            "cursor helper",
            "cursor.app",
            "hermes_kernel",
            "hermes-toolchain",
        )
    ):
        return None
    argv0 = cmd.split()[0] if cmd.split() else ""
    base = Path(argv0).name.lower()
    if base in {"claude", "claude.exe"} or base.startswith("claude-"):
        return "claude-code"
    if base in {"agent", "cursor-agent"} or "cursor agent" in title.lower():
        return "cursor"
    if base in {"codex", "codex.exe"}:
        return "codex"
    if "herm-tui" in blob or "tui_gateway" in blob:
        return "hermes"
    if base == "hermes" and "toolchain" not in blob:
        return "hermes"
    if base == "pi" or blob.startswith("pi ") or blob.endswith("/pi"):
        return "pi"
    if base == "nvim" and "atop-vi" in blob:
        return "atop-vi"
    if base == "atop-tui":
        return "atop"
    return None


def classify_state(activity: str, title: str = "") -> str:
    blob = f"{activity} {title}".lower()
    if any(h in blob for h in ("compact", "compacting")):
        return "compact"
    if any(h in blob for h in BUSY_HINTS):
        return "busy"
    if any(h in blob for h in IDLE_HINTS):
        return "idle"
    if activity.strip():
        return "live"
    return "idle"


def parse_ps_table(text: str) -> dict[str, dict[str, str]]:
    procs: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        pid, ppid = parts[0], parts[1]
        cmd = parts[2] if len(parts) > 2 else ""
        procs[pid] = {"pid": pid, "ppid": ppid, "cmd": cmd}
    return procs


def walk_children(root: str, procs: dict[str, dict[str, str]], depth: int = 5) -> list[dict[str, str]]:
    kids = {p["ppid"]: [] for p in procs.values()}
    for p in procs.values():
        kids.setdefault(p["ppid"], []).append(p)
    out: list[dict[str, str]] = []
    stack = [(root, 0)]
    seen: set[str] = set()
    while stack:
        pid, d = stack.pop()
        if d > depth or pid in seen:
            continue
        seen.add(pid)
        if pid in procs and pid != root:
            out.append(procs[pid])
        for child in kids.get(pid, []):
            stack.append((child["pid"], d + 1))
    return out


def load_ps() -> dict[str, dict[str, str]]:
    text = _run(["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "command="])
    if not text:
        text = _run(["ps", "-ax", "-o", "pid,ppid,command"])
    return parse_ps_table(text)


def capture_pane(target: str, lines: int = 24) -> str:
    raw = _run(["tmux", "capture-pane", "-t", target, "-p", "-J", "-S", f"-{lines}"])
    cleaned = [redact(ln.rstrip()) for ln in raw.splitlines() if ln.strip()]
    return "\n".join(cleaned[-8:])


def last_activity(capture: str) -> str:
    picked = ""
    for line in reversed(capture.splitlines()):
        s = line.strip()
        if not s:
            continue
        if set(s) <= {"─", "━", " ", "-", "=", "·", "│", "┌", "└", "┐", "┘"}:
            continue
        low = s.lower()
        if any(c in low for c in CHROME):
            continue
        if "0 running" in low:
            continue
        picked = s[:160]
        break
    return picked


def skill_roots(h: Path) -> list[Path]:
    return [
        h / ".pi/agent/skills",
        h / ".codex/skills",
        h / ".local/share/hermes-agents/chief-of-staff/skills",
        h / ".local/share/hermes-agents/chief-of-staff-work/skills",
        h / ".agents/skills",
        h / ".cursor/skills",
    ]


def skill_present(h: Path, name: str) -> list[str]:
    hits = []
    for root in skill_roots(h):
        p = root / name
        if p.exists():
            hits.append(str(p))
    return hits


def layer_rows(h: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lid, family, names in LAYER_SKILLS:
        hits: list[str] = []
        for name in names:
            hits.extend(skill_present(h, name))
        extra = ""
        status = "ok" if hits else "missing"
        if lid == "infra-herm":
            fork = h / "src/profile/bin/hermes/fork-env.sh"
            if fork.is_file():
                extra = str(fork)
                if not hits:
                    status = "warn"
            elif not hits:
                status = "missing"
        if lid == "infra-host":
            reg = h / "src/profile/bin/tmux/hosts/registry.conf"
            if reg.is_file():
                extra = str(reg)
                if not hits:
                    status = "warn"
        if lid == "atop-vi":
            vi = h / "src/profile/bin/atop/vi"
            if vi.is_file():
                extra = str(vi)
                status = "ok" if hits or vi.is_file() else status
        detail = ",".join(hits[:3]) or extra or "not linked"
        rows.append({"id": lid, "family": family, "status": status, "detail": detail})

    jobs = h / ".pi/agent/jobs"
    if jobs.is_dir():
        rows.append({"id": "job-bus", "family": "bus", "status": "ok", "detail": str(jobs)})
    else:
        rows.append({"id": "job-bus", "family": "bus", "status": "missing", "detail": str(jobs)})

    for hid, rel in HARNESS_HOMES:
        p = h / rel
        if not p.is_dir():
            rows.append({"id": hid, "family": "harness", "status": "missing", "detail": str(p)})
            continue
        names = sorted(x.name for x in p.iterdir() if not x.name.startswith("."))
        status = "ok" if names else "warn"
        if hid.startswith("hermes-") and "autonomous-ai-agents" not in names:
            status = "warn"
        rows.append(
            {
                "id": hid,
                "family": "harness",
                "status": status,
                "detail": f"{p} n={len(names)}",
            }
        )
    return rows


def parse_tmux_panes(text: str) -> list[dict[str, str]]:
    panes = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        panes.append(
            {
                "target": parts[0].strip(),
                "pid": parts[1].strip(),
                "cmd": parts[2].strip(),
                "title": parts[3].strip() if len(parts) > 3 else "",
                "cwd": parts[4].strip() if len(parts) > 4 else "",
            }
        )
    return panes


def load_tmux_panes() -> list[dict[str, str]]:
    text = _run(
        [
            "tmux",
            "list-panes",
            "-a",
            "-F",
            "#{session_name}:#{window_index}.#{pane_index}\t#{pane_pid}\t"
            "#{pane_current_command}\t#{pane_title}\t#{pane_current_path}",
        ]
    )
    return parse_tmux_panes(text)


def load_jobs(h: Path, limit: int = 80) -> list[dict[str, Any]]:
    root = h / ".pi/agent/jobs"
    if not root.is_dir():
        return []
    files: list[Path] = []
    for dirpath, _dirs, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(".status.json"):
                files.append(Path(dirpath) / name)
        if len(files) >= 400:
            break
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    out = []
    for path in files[:limit]:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "job_id": rec.get("jobId") or rec.get("id") or path.stem,
                "status": rec.get("status") or "",
                "stream": rec.get("stream") or "",
                "project": rec.get("project") or "",
                "summary": (rec.get("message") or rec.get("summary") or "")[:160],
                "sid": rec.get("sessionId") or rec.get("sid") or path.parent.name,
                "path": str(path),
            }
        )
    return out


def session_from_pane(
    pane: dict[str, str],
    procs: dict[str, dict[str, str]],
    jobs: list[dict[str, Any]],
    prompts: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    kids = walk_children(pane["pid"], procs)
    harness = classify_cmd(pane["cmd"], pane["title"])
    agent_cmd = pane["cmd"]
    for kid in kids:
        h = classify_cmd(kid["cmd"])
        if h:
            harness = h
            agent_cmd = kid["cmd"]
            break
    if harness is None:
        return None
    capture = capture_pane(pane["target"])
    activity = last_activity(capture)
    state = classify_state(activity, pane["title"])
    job = next((j for j in jobs if j.get("sid") and j["sid"] in (pane["target"], f"tmux:{pane['target']}")), None)
    prompt = prompts.get(pane["target"]) or prompts.get(f"tmux:{pane['target']}")
    cwd = pane.get("cwd") or ""
    project = Path(cwd).name if cwd else "unscoped"
    return {
        "sid": f"tmux:{pane['target']}",
        "tmux_target": pane["target"],
        "harness": harness,
        "profile": harness,
        "project": project or "unscoped",
        "pid": pane["pid"],
        "cwd": cwd,
        "title": pane.get("title") or agent_cmd[:80],
        "state": state,
        "activity": activity,
        "age_s": 0,
        "cmd": agent_cmd[:120],
        "prompt": prompt,
        "job": {"id": job["job_id"], "status": job["status"]} if job else None,
    }


def load_orphan_procs(
    procs: dict[str, dict[str, str]],
    claimed: set[str],
) -> list[dict[str, Any]]:
    rows = []
    claimed_all = set(claimed)
    for pid, rec in procs.items():
        if pid in claimed_all:
            continue
        harness = classify_cmd(rec["cmd"])
        if not harness:
            continue
        # skip children of claimed pane pids
        cur = rec.get("ppid")
        skip = False
        for _ in range(8):
            if not cur or cur in {"0", "1"}:
                break
            if cur in claimed_all:
                skip = True
                break
            cur = procs.get(cur, {}).get("ppid")
        if skip:
            continue
        rows.append(
            {
                "sid": f"proc:{pid}",
                "tmux_target": "",
                "harness": harness,
                "profile": harness,
                "project": "unscoped",
                "pid": pid,
                "cwd": "",
                "title": rec["cmd"][:80],
                "state": "live",
                "activity": rec["cmd"][:160],
                "age_s": 0,
                "cmd": rec["cmd"][:120],
                "prompt": None,
                "job": None,
            }
        )
        claimed_all.add(pid)
    return rows


def collect(h: Path | None = None, include_orphans: bool = False) -> dict[str, Any]:
    h = h or home()
    layers = layer_rows(h)
    jobs = load_jobs(h)
    procs = load_ps()
    panes = load_tmux_panes()
    prompts: dict[str, dict[str, Any]] = {}
    sessions: list[dict[str, Any]] = []
    claimed: set[str] = set()
    for pane in panes:
        row = session_from_pane(pane, procs, jobs, prompts)
        if row is None:
            continue
        sessions.append(row)
        claimed.add(pane["pid"])
        for kid in walk_children(pane["pid"], procs):
            claimed.add(kid["pid"])
    if include_orphans:
        sessions.extend(load_orphan_procs(procs, claimed))
    ok = sum(1 for r in layers if r["status"] == "ok")
    warn = sum(1 for r in layers if r["status"] == "warn")
    missing = sum(1 for r in layers if r["status"] == "missing")
    busy = sum(1 for s in sessions if s["state"] == "busy")
    return {
        "schema": SCHEMA,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": os.uname().nodename.split(".")[0],
        "host_class": host_class(h),
        "layers": layers,
        "sessions": sessions,
        "jobs": jobs[:20],
        "counts": {
            "sessions": len(sessions),
            "busy": busy,
            "live": sum(1 for s in sessions if s["state"] in {"live", "busy", "compact"}),
            "idle": sum(1 for s in sessions if s["state"] == "idle"),
            "layers_ok": ok,
            "layers_warn": warn,
            "layers_missing": missing,
            "layers": len(layers),
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    c = data.get("counts") or {}
    lines = [
        "# atop live",
        "",
        f"host `{data.get('host')}` class `{data.get('host_class')}`  "
        f"layers {c.get('layers_ok', 0)}/{c.get('layers', 0)} ok  "
        f"sessions {c.get('sessions', 0)}  busy {c.get('busy', 0)}  "
        f"idle {c.get('idle', 0)}",
        "",
        f"observed {data.get('observed_at')}",
        "",
        "## layers",
        "",
    ]
    for row in data.get("layers") or []:
        lines.append(f"- `{row['status']:<7}` {row['id']:<22} {row.get('detail', '')}")
    lines += ["", "## sessions", ""]
    sess = data.get("sessions") or []
    if not sess:
        lines.append("_no live agent panes_")
    for s in sess:
        act = (s.get("activity") or s.get("title") or "").replace("\t", " ")
        lines.append(
            f"- `{s.get('state', '?'):<7}` {s.get('harness', '?'):<12} "
            f"{s.get('tmux_target') or s.get('sid')}  {act}"
        )
    lines += [
        "",
        "Telescope: sessions + prompt buffers. `<CR>` edit  `<C-r>` refresh  `<leader>fv` picker.",
        "Coordinate via `atop vi <id> get|set --file`. Never send-keys.",
        "",
    ]
    return "\n".join(lines)


def render_text(data: dict[str, Any]) -> str:
    c = data.get("counts") or {}
    lines = [
        f"{data.get('host')} {data.get('host_class')}  "
        f"layers {c.get('layers_ok', 0)}/{c.get('layers', 0)} ok "
        f"{c.get('layers_warn', 0)} warn {c.get('layers_missing', 0)} miss  "
        f"sess {c.get('sessions', 0)} busy {c.get('busy', 0)} idle {c.get('idle', 0)}"
    ]
    lines.append("LAYER\tSTATUS\tDETAIL")
    for row in data.get("layers") or []:
        lines.append(f"{row['id']}\t{row['status']}\t{row.get('detail', '')}")
    lines.append("STATE\tHARNESS\tTARGET\tACTIVITY")
    for s in data.get("sessions") or []:
        lines.append(
            f"{s.get('state')}\t{s.get('harness')}\t{s.get('tmux_target') or s.get('sid')}\t"
            f"{(s.get('activity') or '')[:120]}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="atop live sessions + AOS layers")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--home", type=Path)
    ap.add_argument("--orphans", action="store_true")
    args = ap.parse_args()
    data = collect(args.home, include_orphans=args.orphans)
    if args.markdown:
        text = render_markdown(data)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0
    if args.json or args.out:
        payload = json.dumps(data, indent=2) + "\n"
        if args.out:
            args.out.write_text(payload, encoding="utf-8")
        if args.json or not args.out:
            print(payload, end="")
        return 0
    print(render_text(data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
