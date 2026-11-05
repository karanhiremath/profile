"""Pure fake-conference state machine; no filesystem, process, audio, or network I/O.

All metadata is caller-supplied test data, NOT authenticated authority. A future
live adapter must resolve identities/capabilities from the canonical control plane.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from itertools import pairwise
from typing import Any

STATE = "aos.voice.conference.v1"
CATALOG = "aos.voice.catalog.v1"
TOOL = "aos.voice.tool.v1"
VERBS = {"status", "observe", "steer", "draft"}
ROLES = {"cos": 0, "pm": 1, "pl": 2, "worker": 3, "terminal": 4}
OPERATIONS = {"bind", "connect", "disconnect", "dispatch"}
LIMIT = 131072


class Rejected(Exception):
    """An error with constant, safe-to-display fields, never raw input."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require(condition: bool, code: str = "invalid_schema") -> None:
    if not condition:
        raise Rejected(code, "Input rejected; see the offline voice contract.")


def fields(value: Any, names: set[str]) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == names)
    return value


def identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}", value)
    )


def generation(value: Any) -> bool:
    return type(value) is int and 1 <= value <= 2**53 - 1


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise Rejected("invalid_json", "Non-finite JSON values are not supported.")


def decode(raw: str) -> dict[str, Any]:
    require(len(raw.encode("utf-8")) <= LIMIT, "input_too_large")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError):
        raise Rejected("invalid_json", "Expected one bounded JSON object.") from None
    require(isinstance(value, dict))
    return value


def chain(catalog: dict[str, Any], target: str) -> list[dict[str, Any]]:
    nodes = {node["id"]: node for node in catalog["targets"]}
    require(target in nodes, "unknown_target")
    route: list[dict[str, Any]] = []
    node = nodes[target]
    while True:
        require(node["id"] not in {item["id"] for item in route}, "cycle")
        route.append(node)
        if node["parent"] is None:
            return list(reversed(route))
        require(node["parent"] in nodes, "missing_parent")
        node = nodes[node["parent"]]


def catalog(value: Any) -> dict[str, Any]:
    fields(value, {"schema", "targets"})
    require(value["schema"] == CATALOG)
    require(isinstance(value["targets"], list) and 0 < len(value["targets"]) <= 128)
    ids: set[str] = set()
    locators: set[tuple[Any, ...]] = set()
    for node in value["targets"]:
        fields(
            node,
            {
                "id",
                "domain",
                "host",
                "profile",
                "role",
                "harness",
                "session",
                "generation",
                "parent",
                "capabilities",
                "tmux",
            },
        )
        require(
            all(identifier(node[key]) for key in ("id", "host", "profile", "session"))
        )
        require(node["id"] not in ids, "duplicate_target")
        ids.add(node["id"])
        require(node["domain"] in ("personal", "work"))
        require(isinstance(node["role"], str) and node["role"] in ROLES)
        require(node["harness"] in ("hermes", "pi", "codex", "claude", "none"))
        require(generation(node["generation"]))
        require(node["parent"] is None or identifier(node["parent"]))
        require(isinstance(node["capabilities"], list))
        require(
            all(isinstance(cap, str) and cap in VERBS for cap in node["capabilities"])
        )
        require(len(set(node["capabilities"])) == len(node["capabilities"]))
        if node["domain"] == "personal":
            require(
                not node["profile"].endswith("-work")
                and node["profile"]
                not in {"cosw", "work-cos", "work-notes", "cos-work"},
                "domain_mismatch",
            )
        if node["harness"] == "none":
            require(
                node["role"] == "terminal"
                and set(node["capabilities"]) <= {"status", "observe"},
                "unmanaged_steer",
            )
        fields(node["tmux"], {"server", "session", "window", "pane"})
        require(identifier(node["tmux"]["server"]))
        for key, prefix in (("session", "$"), ("window", "@"), ("pane", "%")):
            require(
                isinstance(node["tmux"][key], str)
                and bool(
                    re.fullmatch(re.escape(prefix) + r"[0-9]{1,9}", node["tmux"][key])
                )
            )
        locator = (
            node["host"],
            *[node["tmux"][key] for key in ("server", "session", "window", "pane")],
        )
        require(locator not in locators, "ambiguous_locator")
        locators.add(locator)
    for node in value["targets"]:
        route = chain(value, node["id"])
        require(route[0]["role"] == "cos", "missing_controller")
        for parent, child in pairwise(route):
            require(parent["domain"] == child["domain"], "domain_mismatch")
            require(ROLES[parent["role"]] < ROLES[child["role"]], "invalid_cascade")
            require(
                set(child["capabilities"]) <= set(parent["capabilities"]),
                "capability_widening",
            )
    return deepcopy(value)


def initial(value: Any) -> dict[str, Any]:
    return {
        "schema": STATE,
        "mode": "fake",
        "catalog": catalog(value),
        "binding": None,
        "connection": "disconnected",
        "seen": [],
        "receipt": None,
    }


def state(value: Any) -> dict[str, Any]:
    fields(
        value, {"schema", "mode", "catalog", "binding", "connection", "seen", "receipt"}
    )
    require(value["schema"] == STATE and value["mode"] == "fake", "offline_only")
    catalog(value["catalog"])
    require(value["connection"] in ("connected", "disconnected"))
    require(isinstance(value["seen"], list) and len(value["seen"]) <= 128)
    require(all(identifier(item) for item in value["seen"]))
    require(len(set(value["seen"])) == len(value["seen"]))
    binding = value["binding"]
    if binding is None:
        require(value["connection"] == "disconnected" and not value["seen"])
    else:
        fields(binding, {"domain", "route"})
        require(binding["domain"] in ("personal", "work"))
        require(isinstance(binding["route"], list) and 0 < len(binding["route"]) <= 5)
        catalog({"schema": CATALOG, "targets": binding["route"]})
        leaf = binding["route"][-1]
        require(isinstance(leaf, dict) and identifier(leaf.get("id")))
        route = chain(value["catalog"], leaf["id"])
        require(binding["route"] == route, "stale_binding")
        require(
            all(node["domain"] == binding["domain"] for node in route),
            "domain_mismatch",
        )
    receipt = value["receipt"]
    if receipt is not None:
        fields(
            receipt,
            {"operation", "status", "executed", "request_id", "verb", "route", "acks"},
        )
        require(
            receipt["operation"] in OPERATIONS
            and receipt["status"] in ("simulated", "dry_run")
        )
        require(receipt["executed"] is False)
        require(receipt["request_id"] is None or identifier(receipt["request_id"]))
        require(
            receipt["verb"] is None
            or (isinstance(receipt["verb"], str) and receipt["verb"] in VERBS)
        )
        require(isinstance(receipt["route"], list) and len(receipt["route"]) <= 5)
        require(all(identifier(item) for item in receipt["route"]))
        require(isinstance(receipt["acks"], list) and len(receipt["acks"]) <= 6)
        for ack in receipt["acks"]:
            fields(ack, {"target", "state"})
            require(
                identifier(ack["target"])
                and ack["state"] in ("simulated_accepted", "simulated_completed")
            )
    return deepcopy(value)


def receipt(
    operation: str,
    route: list[dict[str, Any]],
    dry_run: bool,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ids = [node["id"] for node in route]
    acks = (
        []
        if dry_run
        else [{"target": target, "state": "simulated_accepted"} for target in ids]
    )
    if not dry_run and operation == "dispatch":
        acks.append({"target": ids[-1], "state": "simulated_completed"})
    return {
        "operation": operation,
        "status": "dry_run" if dry_run else "simulated",
        "executed": False,
        "request_id": request["id"] if request else None,
        "verb": request["verb"] if request else None,
        "route": ids,
        "acks": acks,
    }


def bind(
    value: Any, target: str, revision: int, domain: str, dry_run: bool = False
) -> dict[str, Any]:
    result = state(value)
    require(result["connection"] == "disconnected", "leave_before_rebind")
    require(identifier(target) and generation(revision), "invalid_target")
    route = chain(result["catalog"], target)
    require(route[-1]["generation"] == revision, "stale_generation")
    require(all(node["domain"] == domain for node in route), "domain_mismatch")
    if not dry_run:
        # Snapshot independently: later catalog refreshes must not mutate the pin.
        result["binding"] = {"domain": domain, "route": deepcopy(route)}
        # Keep replay history across leave/rebind. Never silently evict IDs.
    result["receipt"] = receipt("bind", route, dry_run)
    return result


def connection(value: Any, operation: str, dry_run: bool = False) -> dict[str, Any]:
    result = state(value)
    require(operation in {"connect", "disconnect"})
    require(result["binding"] is not None, "not_bound")
    expected = "disconnected" if operation == "connect" else "connected"
    require(result["connection"] == expected, "invalid_connection_state")
    if not dry_run:
        result["connection"] = "connected" if operation == "connect" else "disconnected"
    result["receipt"] = receipt(operation, result["binding"]["route"], dry_run)
    return result


class FakeManagedAgent:
    """Simulate a managed-agent tool callback; never call a provider or harness."""

    def call(self, value: Any, request: Any, dry_run: bool = False) -> dict[str, Any]:
        result = state(value)
        require(
            result["connection"] == "connected" and result["binding"] is not None,
            "not_joined",
        )
        require(isinstance(request, dict))
        names = {"schema", "id", "target", "generation", "verb"}
        require(set(request) in (names, names | {"text"}))
        require(
            request["schema"] == TOOL
            and identifier(request["id"])
            and identifier(request["target"])
        )
        require(generation(request["generation"]))
        require(isinstance(request["verb"], str) and request["verb"] in VERBS)
        if request["verb"] in {"steer", "draft"}:
            require(
                isinstance(request.get("text"), str)
                and 0 < len(request["text"]) <= 4096
                and bool(request["text"].strip())
            )
        else:
            require("text" not in request)
        route = result["binding"]["route"]
        leaf = route[-1]
        require(request["target"] == leaf["id"], "target_not_pinned")
        require(request["generation"] == leaf["generation"], "stale_generation")
        require(
            all(request["verb"] in node["capabilities"] for node in route),
            "capability_denied",
        )
        require(request["id"] not in result["seen"], "replay")
        require(len(result["seen"]) < 128, "history_full")
        if not dry_run:
            result["seen"].append(request["id"])
        # Text is deliberately omitted from output, receipts and events.
        result["receipt"] = receipt("dispatch", route, dry_run, request)
        return result
