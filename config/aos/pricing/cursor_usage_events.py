"""Parse Cursor dashboard usage-events CSV (strategy=tokens).

Official columns (2026-09-15 export):
  Date, User, Cloud Agent ID, Automation ID, Kind, Model, Max Mode,
  Input (w/ Cache Write), Input (w/o Cache Write), Cache Read,
  Output Tokens, Total Tokens, Cost

Kind=Free and Cost=Free mean included quota, not zero spend.
Do not persist User / Cloud Agent ID / Automation ID.
"""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

CALIBRATION_FEE = 0.07
CALIBRATION_USD = 1.45
EXPLICIT_USD_PER_M = {
    "grok-4.6:fast": 1.45,
    "grok-4.6": 0.68,
    "grok-4.6:slow": 0.68,
}

# Together API $/M by bucket. Not Cursor blended token-fee.
TOGETHER_BUCKETS = {
    "deepseek-v4-flash-0731": {
        "input": 0.14,
        "output": 0.28,
        "cache_read": 0.03,
        "cache_write": 0.0,
    },
}

COL_IN_W = "Input (w/ Cache Write)"
COL_IN_WO = "Input (w/o Cache Write)"
COL_CACHE = "Cache Read"
COL_OUT = "Output Tokens"
COL_TOTAL = "Total Tokens"
COL_COST = "Cost"
COL_MODEL = "Model"
COL_KIND = "Kind"
COL_DATE = "Date"

DEFAULT_LEDGER = Path.home() / ".local/share/aos/spend/cursor-usage-events.v1.json"


def classify(model: str) -> str:
    raw = (model or "").lower().replace("_", "-")
    bare = raw.split("/")[-1]
    if "deepseek-v4-flash-0731" in raw:
        return "deepseek-v4-flash-0731"
    if "grok-4.6" in bare and "fast" in bare:
        return "grok-4.6:fast"
    if "grok-4.6" in bare:
        return "grok-4.6"
    if "composer-2" in bare and "fast" in bare:
        return "composer-2:fast"
    if "composer-2.5" in bare and "fast" in bare:
        return "composer-2:fast"
    if "composer-2" in bare or "composer-2.5" in bare:
        return "composer-2"
    if "composer" in bare:
        return "composer"
    if "claude" in bare and "opus" in bare and "fast" in bare:
        return "claude-4.6-opus:fast"
    if "claude" in bare and "opus" in bare:
        return "claude-4.6-opus"
    if "claude" in bare and "sonnet" in bare:
        return "claude-4.6-sonnet"
    if "claude" in bare and "haiku" in bare:
        return "claude-4.5-haiku"
    return bare


def bucket_rates(classified: str) -> dict[str, float] | None:
    return TOGETHER_BUCKETS.get(classified)


def usd_per_m(classified: str, fees: dict[str, float] | None = None) -> float:
    buckets = bucket_rates(classified)
    if buckets:
        return buckets["input"]
    if classified in EXPLICIT_USD_PER_M:
        return EXPLICIT_USD_PER_M[classified]
    pct = (fees or {}).get(classified)
    if pct is None:
        return 0.0
    return pct / CALIBRATION_FEE * CALIBRATION_USD


def status_of(classified: str, fees: dict[str, float] | None = None) -> str:
    if classified in TOGETHER_BUCKETS or classified in EXPLICIT_USD_PER_M:
        return "explicit"
    if classified in (fees or {}):
        return "estimated"
    return "unknown"


def _num(value: Any) -> float:
    text = str(value or "").replace(",", "").replace("$", "").strip()
    if not text or text.lower() == "free":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def partition_row(row: dict[str, str]) -> dict[str, int]:
    in_wo = int(_num(row.get(COL_IN_WO)))
    in_w = int(_num(row.get(COL_IN_W)))
    cache_read = int(_num(row.get(COL_CACHE)))
    output = int(_num(row.get(COL_OUT)))
    cache_write = max(0, in_w - in_wo)
    billed = int(_num(row.get(COL_TOTAL)))
    if billed <= 0:
        billed = in_wo + output + cache_read + cache_write
    return {
        "input": in_wo,
        "output": output,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "billed": billed,
    }


def parse_export_url(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    def first(name: str) -> str:
        vals = q.get(name) or []
        return vals[0] if vals else ""
    start = first("startDate")
    end = first("endDate")
    return {
        "team_id_present": bool(first("teamId")),
        "is_enterprise": first("isEnterprise").lower() == "true",
        "start_ms": int(start) if start.isdigit() else None,
        "end_ms": int(end) if end.isdigit() else None,
        "strategy": first("strategy") or "tokens",
    }


def iter_rows(text: str) -> Iterable[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        yield row


def aggregate_rows(
    rows: Iterable[dict[str, str]],
    fees: dict[str, float] | None = None,
) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    dates: list[str] = []
    events = 0
    kinds: dict[str, int] = defaultdict(int)
    dashboard_cost_nonzero = 0
    for row in rows:
        events += 1
        kinds[str(row.get(COL_KIND) or "")] += 1
        if _num(row.get(COL_COST)) > 0:
            dashboard_cost_nonzero += 1
        if row.get(COL_DATE):
            dates.append(row[COL_DATE])
        classified = classify(str(row.get(COL_MODEL) or ""))
        tokens = partition_row(row)
        bucket = by_model.setdefault(
            classified,
            {
                "classified": classified,
                "events": 0,
                "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "billed": 0},
                "source_models": {},
            },
        )
        bucket["events"] += 1
        for key in ("input", "output", "cache_read", "cache_write", "billed"):
            bucket["tokens"][key] += tokens[key]
        src = str(row.get(COL_MODEL) or "")
        bucket["source_models"][src] = bucket["source_models"].get(src, 0) + 1

    for classified, bucket in by_model.items():
        rate = usd_per_m(classified, fees)
        billed = bucket["tokens"]["billed"]
        per = rate / 1_000_000.0
        fee = (fees or {}).get(classified)
        bucket["cost"] = {
            "usd_per_m": rate,
            "fee_pct": fee,
            "status": status_of(classified, fees),
            "api_equivalent_usd": billed * per,
            "dashboard_cost_usd": 0.0,
        }
        if fee is not None:
            bucket["cost"]["fee_weighted_tokens"] = billed * fee

    cursor = {
        "events": 0,
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "billed": 0},
        "api_equivalent_usd": 0.0,
    }
    for bucket in by_model.values():
        cursor["events"] += bucket["events"]
        for key in cursor["tokens"]:
            cursor["tokens"][key] += bucket["tokens"][key]
        cursor["api_equivalent_usd"] += float(bucket["cost"]["api_equivalent_usd"])

    return {
        "schema": "aos.cursor-usage-events.v1",
        "events": events,
        "kinds": dict(kinds),
        "dashboard_cost_nonzero": dashboard_cost_nonzero,
        "dashboard_cost_is_included": dashboard_cost_nonzero == 0,
        "window": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
        },
        "by_model": by_model,
        "by_harness": {"cursor": cursor},
    }


def ingest_csv_text(
    text: str,
    *,
    fees: dict[str, float] | None = None,
    source: str = "cursor-dashboard-export",
    export_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = aggregate_rows(iter_rows(text), fees)
    payload["source"] = source
    payload["ingested_at"] = datetime.now(timezone.utc).isoformat()
    if export_meta:
        payload["export"] = export_meta
    return payload


def ingest_csv_path(
    path: Path,
    *,
    fees: dict[str, float] | None = None,
    export_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ingest_csv_text(
        path.read_text(encoding="utf-8"),
        fees=fees,
        source=str(path),
        export_meta=export_meta,
    )


def write_ledger(payload: dict[str, Any], dest: Path = DEFAULT_LEDGER) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
