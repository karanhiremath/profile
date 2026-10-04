"""Fleetops snapshot for the Cos-voice surface. atop dump + tmux + attach inventory."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ATOP = shutil.which("atop") or str(Path.home() / ".local/bin/atop")
TMUX = shutil.which("tmux") or "/opt/homebrew/bin/tmux"
TAILSCALE = shutil.which("tailscale") or "/opt/homebrew/bin/tailscale"
HOSTCTL_YAML = Path(__file__).resolve().parents[1] / "hostctl" / "interactive.yaml"
DAG_PATH = Path.home() / "src/notes/03_tech/agentic-os/fleet/schemas/dependency-dag.md"
OTEL_EVENTS = Path.home() / ".pi/agent/otel/agent-events.jsonl"

WORK_LANES = [f"ao{i}" for i in range(5)] + [f"infra{i}" for i in range(5)]
PLAN_LANES = [f"cos-ao{i}" for i in range(5)] + [f"cos-infra{i}" for i in range(5)]
INFRA_LANES = [f"infra{i}" for i in range(5)]
OPERATOR = {"cos", "cos-mini", "atop", "atop-coord"}
SANDBOX_NAMES = {"mac-s", "oma-s"}
GATE_ROW = re.compile(
    r"^\|\s*`?(G-[A-Z0-9-]+)`?\s*\|\s*(.*?)\s*\|\s*.*?\s*\|\s*(.*?)\s*\|\s*$"
)
WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
CODE = re.compile(r"`([^`]+)`")


def _run(argv: list[str], timeout: float = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _tmux_sessions() -> list[dict[str, Any]]:
    proc = _run(
        [
            TMUX,
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_attached}\t#{session_windows}",
        ]
    )
    if proc.returncode != 0:
        return []
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rows.append(
            {
                "name": parts[0],
                "attached": parts[1] not in {"0", ""},
                "windows": int(parts[2] or 0),
            }
        )
    return rows


def _atop_dump() -> dict[str, Any]:
    if not Path(ATOP).is_file():
        return {}
    proc = _run([ATOP, "dump"], timeout=12)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def atop_sessions() -> list[dict[str, Any]]:
    rows = []
    for row in _atop_dump().get("sessions") or []:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _session_titles(atop: dict[str, Any]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for row in atop.get("sessions") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()[:120]
        if not title:
            continue
        tmux = str(row.get("tmux_target") or "")
        sid = str(row.get("sid") or "")
        name = tmux.split(":")[0] if tmux else ""
        if not name and sid.startswith("tmux:"):
            name = sid.split(":")[1] if ":" in sid[5:] else ""
        if name and name not in titles:
            titles[name] = title
    return titles


def _gate_state(cell: str) -> str:
    low = (cell or "").lower()
    if "in flight" in low:
        return "in flight"
    if "unknown" in low:
        return "unknown"
    if "closed" in low:
        return "closed"
    if "open" in low:
        return "open"
    return "unknown"


def _gate_owner(cell: str) -> str:
    text = WIKILINK.sub(r"\1", cell or "")
    text = CODE.sub(r"\1", text)
    parts = [p.strip() for p in re.split(r"\s*\+\s*|,", text) if p.strip()]
    return ", ".join(parts)[:80]


def graph_gates(path: Path | None = None) -> dict[str, Any]:
    src = path or DAG_PATH
    if not src.is_file():
        return {"ok": False, "source": str(src), "gates": []}
    gates: list[dict[str, str]] = []
    try:
        text = src.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "source": str(src), "gates": [], "error": str(exc)}
    for line in text.splitlines():
        if "| Gate |" in line or line.startswith("|---"):
            continue
        match = GATE_ROW.match(line)
        if not match:
            continue
        gates.append(
            {
                "id": match.group(1),
                "owner": _gate_owner(match.group(2)),
                "state": _gate_state(match.group(3)),
            }
        )
    return {"ok": bool(gates), "source": src.name, "gates": gates}


def _tailscale_peers() -> list[dict[str, Any]]:
    if not Path(TAILSCALE).is_file():
        return []
    proc = _run([TAILSCALE, "status", "--json"], timeout=6)
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    out = []
    self = payload.get("Self") or {}
    if self:
        out.append(
            {
                "name": self.get("HostName") or "self",
                "online": bool(self.get("Online")),
                "os": self.get("OS") or "",
                "role": "self",
            }
        )
    for peer in (payload.get("Peer") or {}).values():
        name = peer.get("HostName") or peer.get("DNSName") or ""
        if not name:
            continue
        out.append(
            {
                "name": name,
                "online": bool(peer.get("Online")),
                "os": peer.get("OS") or "",
                "role": "peer",
            }
        )
    return out


def _cos_live(sessions: list[dict[str, Any]], atop: dict[str, Any]) -> dict[str, Any]:
    tmux_cos = next((s for s in sessions if s["name"] == "cos"), None)
    hermes = []
    for row in atop.get("sessions") or []:
        if not isinstance(row, dict):
            continue
        harness = str(row.get("harness") or "")
        if harness in {"hermes", "herm-tui"}:
            hermes.append(
                {
                    "sid": row.get("sid"),
                    "tmux": row.get("tmux_target"),
                    "title": row.get("title"),
                }
            )
    return {
        "tmux": tmux_cos,
        "hermes_sessions": hermes,
        "herm_tui_live": bool(hermes),
        "note": (
            "Cos herm-tui is live"
            if hermes
            else "Cos tmux exists but is not herm-tui; steers persist to inbox"
            if tmux_cos
            else "No Cos tmux session"
        ),
    }


def _card(session: dict[str, Any], title: str = "", role: str = "") -> dict[str, Any]:
    name = session.get("name") or ""
    return {
        "name": name,
        "attached": bool(session.get("attached")),
        "windows": session.get("windows") or 0,
        "live": True,
        "blocked": name in OPERATOR or str(name).startswith("cos-") or str(name).startswith("atop"),
        "title": title[:120],
        "role": role,
    }


def _named_cards(
    names: list[str],
    live: dict[str, dict[str, Any]],
    titles: dict[str, str],
    role: str,
) -> list[dict[str, Any]]:
    cards = []
    for name in names:
        if name in live:
            cards.append(_card(live[name], titles.get(name, ""), role))
        else:
            cards.append(
                {
                    "name": name,
                    "attached": False,
                    "windows": 0,
                    "live": False,
                    "blocked": name in OPERATOR or name.startswith("cos-") or name.startswith("atop"),
                    "title": titles.get(name, ""),
                    "role": role,
                }
            )
    return cards


def snapshot() -> dict[str, Any]:
    sessions = _tmux_sessions()
    live = {s["name"]: s for s in sessions}
    names = set(live)
    atop = _atop_dump()
    titles = _session_titles(atop)
    jobs = [j for j in (atop.get("jobs") or []) if isinstance(j, dict)]
    job_status = Counter(str(j.get("status") or "unknown") for j in jobs)
    work = _named_cards(WORK_LANES, live, titles, "work")
    plan = _named_cards(PLAN_LANES, live, titles, "plan")
    infra = _named_cards(INFRA_LANES, live, titles, "infra")
    operator = _named_cards(sorted(n for n in names if n in OPERATOR), live, titles, "operator")
    sandbox_names = sorted(n for n in names if n.endswith("-s") or n in SANDBOX_NAMES)
    sandboxes = _named_cards(sandbox_names, live, titles, "sandbox")
    peers = _tailscale_peers()
    for row in atop.get("hosts") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if not name or any(p.get("name") == name for p in peers):
            continue
        peers.append(
            {
                "name": name,
                "online": True,
                "os": "",
                "role": str(row.get("kind") or "atop"),
            }
        )
    oma = next((p for p in peers if "omarchy" in str(p.get("name") or "").lower()), None)
    graph = graph_gates()
    return {
        "ok": True,
        "host": socket.gethostname(),
        "cos": _cos_live(sessions, atop),
        "atop_tmux": next((s for s in sessions if s["name"] == "atop"), None),
        "titles": titles,
        "lanes": {
            "work_live": [c["name"] for c in work if c["live"]],
            "plan_live": [c["name"] for c in plan if c["live"]],
            "operator": [c["name"] for c in operator],
            "sandboxes": [c["name"] for c in sandboxes],
            "work": work,
            "plan": plan,
            "infra": infra,
        },
        "work": work,
        "plan": plan,
        "infra": infra,
        "operator": operator,
        "sandboxes": sandboxes,
        "jobs": {
            "counts": dict(job_status),
            "running": [
                {
                    "id": j.get("job_id"),
                    "project": j.get("project"),
                    "status": "running",
                    "summary": (j.get("summary") or "")[:160],
                }
                for j in jobs
                if j.get("status") == "running"
            ],
            "recent": [
                {
                    "id": j.get("job_id"),
                    "project": j.get("project"),
                    "status": j.get("status"),
                    "summary": (j.get("summary") or "")[:160],
                }
                for j in jobs[:12]
            ],
        },
        "hosts": peers,
        "graph": graph,
        "oma_online": bool(oma and oma.get("online")),
        "wasm_tunnel": "termix :18787 → :8787",
        "blocked_send_keys": ["cos", "cos-*", "atop*"],
    }


def one_line(snap: dict[str, Any] | None = None) -> str:
    data = snap or snapshot()
    cos = data.get("cos") or {}
    work = data.get("work") or []
    live = sum(1 for row in work if row.get("live"))
    running = (data.get("jobs") or {}).get("running") or []
    return (
        f"{cos.get('note') or 'Cos unknown'}; {live}/{len(work)} work live; "
        f"{len(running)} running jobs"
    )[:180]


def role_for(session: str) -> str:
    name = (session or "").split(":")[0]
    if name in INFRA_LANES:
        return "infra"
    if name in WORK_LANES:
        return "work"
    if name in PLAN_LANES:
        return "plan"
    if name in OPERATOR or name.startswith("atop"):
        return "operator"
    if name.endswith("-s") or name in SANDBOX_NAMES:
        return "sandbox"
    return "lane"


def phone_layers(
    snap: dict[str, Any],
    catalog: dict[str, Any],
    prompts: list[dict[str, Any]],
) -> dict[str, Any]:
    titles = snap.get("titles") or {}

    def layer(layer_id: str, title: str, summary: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
        return {"id": layer_id, "title": title, "summary": summary, "cards": cards}

    def session_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cards = []
        for row in rows:
            cards.append(
                {
                    "title": row.get("name") or "?",
                    "meta": row.get("role") or "",
                    "state": "live" if row.get("live") else "down",
                    "detail": (row.get("title") or ("attached" if row.get("attached") else "idle"))[:160],
                }
            )
        return cards

    hosts = snap.get("hosts") or []
    jobs = snap.get("jobs") or {}
    running = jobs.get("running") or []
    recent = jobs.get("recent") or []
    graph = snap.get("graph") or {}
    gates = graph.get("gates") or []
    layers = [
        layer(
            "hosts",
            "Hosts",
            f"{sum(1 for h in hosts if h.get('online'))} online · wasm {snap.get('wasm_tunnel') or ''}",
            [
                {
                    "title": h.get("name") or "host",
                    "meta": h.get("os") or h.get("role") or "",
                    "state": "online" if h.get("online") else "offline",
                    "detail": h.get("role") or "",
                }
                for h in hosts
            ],
        ),
        layer(
            "jobs",
            "Jobs",
            f"{len(running)} running · {jobs.get('counts') or {}}",
            [
                {
                    "title": str(j.get("id") or "job"),
                    "meta": str(j.get("project") or ""),
                    "state": str(j.get("status") or "unknown"),
                    "detail": str(j.get("summary") or "")[:160],
                }
                for j in (running + [j for j in recent if j.get("status") != "running"])[:12]
            ],
        ),
        layer("work", "Work", f"{sum(1 for r in (snap.get('work') or []) if r.get('live'))} live", session_cards(snap.get("work") or [])),
        layer("plan", "Plan", f"{sum(1 for r in (snap.get('plan') or []) if r.get('live'))} live", session_cards(snap.get("plan") or [])),
        layer("infra", "Infra", f"{sum(1 for r in (snap.get('infra') or []) if r.get('live'))} live", session_cards(snap.get("infra") or [])),
        layer("operator", "Operator", "send-keys blocked", session_cards(snap.get("operator") or [])),
        layer("sandboxes", "Sandboxes", f"{len(snap.get('sandboxes') or [])} up", session_cards(snap.get("sandboxes") or [])),
        layer("otel", "OTEL", "atop dump + local events", otel_surface(snap).get("cards") or []),
        layer(
            "graph",
            "Graph gates",
            f"{sum(1 for g in gates if g.get('state') == 'open')} open" if gates else "unparsed",
            [
                {
                    "title": g.get("id") or "gate",
                    "meta": g.get("owner") or "",
                    "state": g.get("state") or "unknown",
                    "detail": g.get("owner") or "",
                }
                for g in gates
            ],
        ),
    ]
    agents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lane in catalog.get("lanes") or []:
        family = str(lane.get("family") or "")
        for sess in lane.get("sessions") or []:
            name = str(sess.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            agents.append(
                {
                    "id": name,
                    "session": name,
                    "family": family,
                    "role": role_for(name),
                    "live": bool(sess.get("live")),
                    "blocked": bool(sess.get("blocked")),
                    "title": titles.get(name) or "",
                }
            )
    for row in (snap.get("operator") or []) + (snap.get("sandboxes") or []):
        name = str(row.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        agents.append(
            {
                "id": name,
                "session": name,
                "family": row.get("role") or "operator",
                "role": role_for(name),
                "live": bool(row.get("live")),
                "blocked": bool(row.get("blocked")),
                "title": titles.get(name) or row.get("title") or "",
            }
        )
    return {"ok": True, "layers": layers, "agents": agents, "prompts": prompts}


def _otel_file_cards(limit: int = 200) -> list[dict[str, Any]]:
    """Count recent agent.otel events. No raw_ref / session dumps."""
    if not OTEL_EVENTS.is_file():
        return [
            {
                "title": "agent.otel",
                "meta": str(OTEL_EVENTS),
                "state": "idle",
                "detail": "No ~/.pi/agent/otel events yet",
            }
        ]
    try:
        lines = OTEL_EVENTS.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError as exc:
        return [
            {
                "title": "agent.otel",
                "meta": "read error",
                "state": "blocked",
                "detail": str(exc)[:160],
            }
        ]
    types: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    last_type = ""
    last_status = ""
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        event_type = str(row.get("event_type") or "event")
        status = str(row.get("status") or "")
        types[event_type] += 1
        if status:
            statuses[status] += 1
        last_type = event_type
        last_status = status
    top = ", ".join(f"{name} {count}" for name, count in types.most_common(4)) or "no events"
    return [
        {
            "title": "agent.otel",
            "meta": f"{len(lines)} recent",
            "state": "live" if lines else "idle",
            "detail": f"{top}. last {last_type} {last_status}".strip(),
        }
    ]


def otel_surface(snap: dict[str, Any] | None = None) -> dict[str, Any]:
    """Phone OTEL/metrics cards from atop dump + local otel file. No new collector."""
    data = snap or snapshot()
    jobs = data.get("jobs") or {}
    running = jobs.get("running") or []
    counts = jobs.get("counts") or {}
    cos = data.get("cos") or {}
    cards: list[dict[str, Any]] = [
        {
            "title": "Jobs",
            "meta": "atop dump",
            "state": "running" if running else "idle",
            "detail": f"{len(running)} running · {counts}",
        }
    ]
    for job in running[:8]:
        cards.append(
            {
                "title": str(job.get("id") or job.get("job_id") or "job"),
                "meta": str(job.get("project") or ""),
                "state": str(job.get("status") or "running"),
                "detail": str(job.get("summary") or "")[:160],
            }
        )
    herm_live = bool(cos.get("herm_tui_live"))
    cards.append(
        {
            "title": "Cos herm-tui",
            "meta": "operator",
            "state": "live" if herm_live else "blocked",
            "detail": str(cos.get("note") or "Cos state unknown")[:160],
        }
    )
    cards.append(
        {
            "title": "Omarchy",
            "meta": "peer",
            "state": "online" if data.get("oma_online") else "offline",
            "detail": "peer online" if data.get("oma_online") else "peer offline",
        }
    )
    cards.extend(_otel_file_cards())
    return {
        "ok": True,
        "source": "atop dump + ~/.pi/agent/otel",
        "cards": cards,
        "alerts": [
            card
            for card in cards
            if card.get("state") in {"blocked", "offline", "failed"}
        ],
    }


def spoken(snap: dict[str, Any] | None = None) -> str:
    data = snap or snapshot()
    cos = data.get("cos") or {}
    lanes = data.get("lanes") or {}
    jobs = data.get("jobs") or {}
    running = jobs.get("running") or []
    work_live = lanes.get("work_live") or [r["name"] for r in (data.get("work") or []) if r.get("live")]
    plan_live = lanes.get("plan_live") or [r["name"] for r in (data.get("plan") or []) if r.get("live")]
    parts = [
        f"Host {data.get('host') or 'unknown'}.",
        str(cos.get("note") or "Cos state unknown") + ".",
        f"{len(work_live)} work lanes live, {len(plan_live)} planning lanes.",
    ]
    if data.get("atop_tmux"):
        parts.append("Atop session is up. Send-keys into Cos and Atop stay blocked.")
    else:
        parts.append("Atop tmux is down.")
    if data.get("oma_online"):
        parts.append("Omarchy peer is online.")
    else:
        parts.append("Omarchy peer is offline. Sandboxes are empty.")
    if running:
        proj = running[0].get("project") or "unscoped"
        parts.append(f"{len(running)} job running in {proj}.")
    else:
        parts.append("No running jobs.")
    parts.append("Talk steers Cos inbox through the wasm tunnel, not live TUI keys.")
    return " ".join(parts)
