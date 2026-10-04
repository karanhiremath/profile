#!/usr/bin/env bash
# Shared Termix wrapper helpers. Source only.

termix_wrapper_dir() {
    cd "$(dirname "${BASH_SOURCE[1]}")" && pwd
}

termix_lib_dir() {
    cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

termix_default_compose_dir() {
    printf '%s\n' "${TERMIX_COMPOSE_DIR:-$HOME/Documents/Codex/2026-09-11/start-claude-cli-remote-control}"
}

termix_local_url() {
    printf '%s\n' "${TERMIX_LOCAL_URL:-http://127.0.0.1:8080}"
}

termix_desired_proxy() {
    printf '%s\n' "${TERMIX_SERVE_PROXY:-http://127.0.0.1:8080}"
}

termix_serve_https_port() {
    printf '%s\n' "${TERMIX_SERVE_HTTPS_PORT:-443}"
}

termix_tailnet_ip() {
    termix_need_cmd tailscale
    tailscale ip -4 | head -1
}

termix_need_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "termix: missing required command: ${cmd}" >&2
        return 1
    fi
}

termix_magic_dns() {
    termix_need_cmd tailscale
    tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'
}

termix_tailnet_url() {
    local host port
    host="$(termix_magic_dns)"
    port="$(termix_serve_https_port)"
    if [ "$port" = "443" ]; then
        printf 'https://%s\n' "$host"
    else
        printf 'https://%s:%s\n' "$host" "$port"
    fi
}

termix_health_url() {
    printf '%s/health\n' "$(termix_local_url | sed 's:/*$::')"
}

termix_wait_healthy() {
    local url attempts sleep_s
    url="$(termix_health_url)"
    attempts="${TERMIX_HEALTH_ATTEMPTS:-30}"
    sleep_s="${TERMIX_HEALTH_SLEEP:-1}"
    while [ "$attempts" -gt 0 ]; do
        if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts - 1))
        sleep "$sleep_s"
    done
    echo "termix: local endpoint is not healthy at ${url}" >&2
    return 1
}

termix_config_dir() {
    if [ -n "${XDG_CONFIG_HOME:-}" ]; then
        printf '%s\n' "${XDG_CONFIG_HOME}/termix"
        return
    fi
    case "$(uname -s)" in
        Darwin) printf '%s\n' "${HOME}/Library/Application Support/termix" ;;
        *) printf '%s\n' "${HOME}/.config/termix" ;;
    esac
}

termix_config_file() {
    printf '%s/config.json\n' "$(termix_config_dir)"
}

termix_ensure_cli_url() {
    local url config
    url="$1"
    config="$(termix_config_file)"
    mkdir -p "$(dirname "$config")"
    python3 - "$config" "$url" <<'PY'
import json
import os
import sys

path, url = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except json.JSONDecodeError:
        data = {}

current = str(data.get("url") or "").rstrip("/")
desired = url.rstrip("/")

def managed(value: str) -> bool:
    lowered = value.rstrip("/").lower()
    return (
        not lowered
        or lowered in {"http://127.0.0.1:8080", "http://localhost:8080"}
        or lowered.endswith(".ts.net")
        or ".ts.net:" in lowered
        or "termix.krop.ai" in lowered
    )

if current and current != desired and not managed(current):
    print(current)
    raise SystemExit(0)

data["url"] = desired
os.makedirs(os.path.dirname(path), exist_ok=True)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(data, fh)
    fh.write("\n")
print(desired)
PY
}

termix_resolve_cli() {
    local self candidate
    self="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[1]}")"
    if [ -n "${TERMIX_CLI:-}" ]; then
        printf '%s\n' "$TERMIX_CLI"
        return 0
    fi
    for candidate in /opt/homebrew/bin/termix /usr/local/bin/termix; do
        if [ -e "$candidate" ] && [ "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$candidate")" != "$self" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    while IFS= read -r candidate; do
        [ -z "$candidate" ] && continue
        if [ "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$candidate")" != "$self" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done < <(type -aP termix 2>/dev/null || true)
    echo "termix: official CLI not found; run just termix or npm install -g @termix-cli/cli" >&2
    return 1
}
