#!/usr/bin/env python3
"""Parse Tailscale Serve JSON without enabling Funnel."""

from __future__ import annotations

import json
import sys
from typing import Any


def load(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode()
    raw = raw.strip()
    if not raw or raw == "No serve config":
        return {}
    data = json.loads(raw)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("serve status must be a JSON object")
    return data


def _web_handlers(entry: dict[str, Any]) -> dict[str, Any]:
    handlers = entry.get("Handlers")
    if isinstance(handlers, dict):
        return handlers
    return entry


def root_proxies(doc: dict[str, Any]) -> list[dict[str, str]]:
    web = doc.get("Web") or {}
    out: list[dict[str, str]] = []
    for host, entry in web.items():
        if not isinstance(entry, dict):
            continue
        for path, cfg in _web_handlers(entry).items():
            if path != "/" or not isinstance(cfg, dict):
                continue
            proxy = cfg.get("Proxy")
            if proxy:
                out.append({"host": str(host), "proxy": str(proxy).rstrip("/")})
    return out


def funnel_paths(doc: dict[str, Any]) -> list[str]:
    allow = doc.get("AllowFunnel") or {}
    enabled: list[str] = []
    for host, paths in allow.items():
        if isinstance(paths, dict):
            nested = paths.get("Handlers")
            items = nested.items() if isinstance(nested, dict) else paths.items()
            for path, flag in items:
                if path == "Handlers":
                    continue
                if flag:
                    enabled.append(f"{host}{path}")
        elif paths:
            enabled.append(str(host))
    return enabled


def is_empty(doc: dict[str, Any]) -> bool:
    return not root_proxies(doc) and not (doc.get("TCP") or {}) and not (doc.get("Web") or {})


def https_ports(doc: dict[str, Any]) -> list[str]:
    ports: set[str] = set()
    for host in (doc.get("Web") or {}):
        if isinstance(host, str) and ":" in host:
            ports.add(host.rsplit(":", 1)[-1])
    for port in (doc.get("TCP") or {}):
        ports.add(str(port))
    return sorted(ports)


def proxy_matches(doc: dict[str, Any], desired_proxy: str) -> bool:
    desired = desired_proxy.rstrip("/")
    proxies = root_proxies(doc)
    return bool(proxies) and all(item["proxy"] == desired for item in proxies)


def matches_desired(
    doc: dict[str, Any],
    desired_proxy: str,
    https_port: str | None = None,
) -> bool:
    if not proxy_matches(doc, desired_proxy):
        return False
    if https_port is None:
        return True
    return str(https_port) in https_ports(doc)


def summarize(
    doc: dict[str, Any],
    desired_proxy: str,
    https_port: str = "443",
) -> dict[str, Any]:
    proxies = root_proxies(doc)
    port = str(https_port)
    return {
        "empty": is_empty(doc),
        "matches": matches_desired(doc, desired_proxy, port),
        "proxy_matches": proxy_matches(doc, desired_proxy),
        "funnel": funnel_paths(doc),
        "proxies": proxies,
        "https_ports": https_ports(doc),
        "desired": desired_proxy.rstrip("/"),
        "desired_https_port": port,
    }


def main(argv: list[str]) -> int:
    desired = argv[1] if len(argv) > 1 else "http://127.0.0.1:8080"
    https_port = argv[2] if len(argv) > 2 else "443"
    raw = sys.stdin.read()
    print(json.dumps(summarize(load(raw), desired, https_port)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
