"""Fail-closed Pi event validation and cross-harness release evidence gates."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class InvalidEvidence(ValueError):
    """Invalid or incomplete machine evidence; never include raw input in errors."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def pi_evidence(events: list[dict[str, Any]], expected: str) -> dict[str, Any]:
    """Inspect real execution events, not narrated tool calls or replay cards.

    This is a single read-fixture probe, not a full lifecycle/platform gate.
    All raw event content stays out of the returned receipt.
    """
    starts: dict[str, str] = {}
    ends: set[str] = set()
    errors: set[str] = set()
    observed = False
    finished = False
    final = ""
    tokens = 0.0
    cost = 0.0
    usage_known = False
    cost_known = False
    for event in events:
        if not isinstance(event, dict):
            raise InvalidEvidence("event must be an object")
        kind = event.get("type")
        if kind == "tool_execution_start":
            call_id, name = event.get("toolCallId"), event.get("toolName")
            if not isinstance(call_id, str) or not call_id or not isinstance(name, str):
                raise InvalidEvidence("invalid execution identity")
            if call_id in starts or call_id.startswith("cursor-replay-"):
                errors.add("duplicate_or_replay_execution")
            if name != "read":
                errors.add("unexpected_tool")
            starts[call_id] = name
        elif kind == "tool_execution_end":
            call_id = event.get("toolCallId")
            if not isinstance(call_id, str) or call_id not in starts or call_id in ends:
                errors.add("unmatched_execution_result")
                continue
            ends.add(call_id)
            if event.get("isError") is not False or event.get("toolName") != starts[call_id]:
                errors.add("tool_failed")
            result = event.get("result")
            content = result.get("content", []) if isinstance(result, dict) else []
            observed |= any(isinstance(block, dict) and block.get("type") == "text"
                            and expected in str(block.get("text", "")) for block in content)
        elif kind == "message_end":
            message = event.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            if message.get("stopReason") in ("error", "aborted"):
                errors.add("assistant_failed")
            content = message.get("content", [])
            final = "".join(str(block.get("text", "")) for block in content
                            if isinstance(block, dict) and block.get("type") == "text")
            usage = message.get("usage")
            if isinstance(usage, dict):
                values = [usage.get(key) for key in ("input", "output", "cacheRead", "cacheWrite")]
                if all(number(value) for value in values):
                    tokens += sum(values)
                    usage_known = True
                total = (usage.get("cost") or {}).get("total")
                if number(total):
                    cost += total
                    cost_known = True
        elif kind == "agent_end":
            finished = True
    if len(starts) != 1 or set(starts) != ends:
        errors.add("expected_one_completed_read")
    if not observed or expected not in final:
        errors.add("fixture_not_observed")
    if not finished:
        errors.add("agent_not_finished")
    return {
        "schema": "harness.pi-read.v1",
        "status": "failed" if errors else "passed",
        "checks": {"tool_roundtrip": not errors},
        "errors": sorted(errors),
        "metrics": {"tokens": tokens if usage_known else None, "cost_usd": cost if cost_known else None},
        "coverage": ["single_read"],
    }


def release_gate(matrix: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Require exact candidate + profile + platform bindings and all checks.

    Receipts are trusted CI inputs, not signatures or authorization tokens.
    This command NEVER promotes or mutates a host.
    """
    if matrix.get("schema") != "harness.matrix.v1" or not isinstance(matrix.get("lanes"), list) or not matrix["lanes"]:
        raise InvalidEvidence("nonempty matrix required")
    expected: dict[str, dict[str, Any]] = {}
    for lane in matrix["lanes"]:
        if not isinstance(lane, dict) or not isinstance(lane.get("id"), str) or not lane["id"]:
            raise InvalidEvidence("invalid lane")
        if lane["id"] in expected or not isinstance(lane.get("checks"), list) or not lane["checks"]:
            raise InvalidEvidence("duplicate lane or empty checks")
        if any(not isinstance(check, str) or not check for check in lane["checks"]):
            raise InvalidEvidence("invalid check name")
        for key in ("candidate", "profile", "platform", "seat"):
            if not isinstance(lane.get(key), str) or not lane[key]:
                raise InvalidEvidence("lane binding missing")
        expected[lane["id"]] = lane
    actual: dict[str, dict[str, Any]] = {}
    for report in reports:
        if not isinstance(report, dict) or report.get("schema") != "harness.lane.v1":
            raise InvalidEvidence("invalid lane report")
        lane_id = report.get("lane")
        if not isinstance(lane_id, str) or lane_id not in expected or lane_id in actual:
            raise InvalidEvidence("unexpected or duplicate report")
        actual[lane_id] = report
    failures: list[dict[str, str]] = []
    for lane_id, lane in expected.items():
        report = actual.get(lane_id)
        reason = ""
        if report is None:
            reason = "missing"
        elif any(report.get(key) != lane[key] for key in ("candidate", "profile", "platform", "seat")):
            reason = "binding_mismatch"
        elif report.get("status") != "passed" or report.get("mode") != "live":
            reason = "not_live_pass"
        elif not isinstance(report.get("checks"), dict) or any(report["checks"].get(check) is not True for check in lane["checks"]):
            reason = "missing_or_failed_check"
        elif not isinstance(report.get("evidence_sha256"), str) or len(report["evidence_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in report["evidence_sha256"]):
            reason = "missing_evidence_digest"
        else:
            limits = lane.get("limits", {})
            metrics = report.get("metrics", {})
            if not isinstance(limits, dict) or not isinstance(metrics, dict):
                raise InvalidEvidence("invalid metrics or limits")
            for key, maximum in limits.items():
                if not number(maximum):
                    raise InvalidEvidence("invalid metric limit")
                if not number(metrics.get(key)) or metrics[key] > maximum:
                    reason = "metric_missing_or_exceeded"
        if reason:
            failures.append({"lane": lane_id, "reason": reason})
    return {"schema": "harness.gate.v1", "status": "blocked" if failures else "passed",
            "matrix_sha256": digest(matrix), "required": len(expected), "received": len(actual),
            "failures": failures, "mutated": False}
