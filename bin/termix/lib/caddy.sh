#!/usr/bin/env bash
# Tailnet-only pretty-name Caddy for termix.krop.ai. Not the public apps edge.

if [ -z "${TERMIX_LIB_DIR:-}" ]; then
    TERMIX_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
# shellcheck source=common.sh
. "${TERMIX_LIB_DIR}/common.sh"

termix_caddy_dir() {
    printf '%s\n' "${TERMIX_CADDY_DIR:-$HOME/src/krop-infra/infra/edge/termix-tailnet}"
}

termix_caddy_network() {
    printf '%s\n' "${TERMIX_CADDY_NETWORK:-start-claude-cli-remote-control_default}"
}

termix_caddy_url() {
    printf 'https://termix.krop.ai:8444\n'
}

termix_caddy_compose() {
    local dir
    dir="$(termix_caddy_dir)"
    if [ ! -f "${dir}/compose.yaml" ]; then
        echo "termix: internal Caddy compose not found at ${dir}/compose.yaml" >&2
        return 1
    fi
    if [ ! -f "${dir}/.env" ]; then
        echo "termix: missing ${dir}/.env (copy .env.example; Namecheap DNS-01)" >&2
        return 1
    fi
    if command -v docker >/dev/null 2>&1; then
        (cd "$dir" && docker compose --env-file .env "$@")
    elif command -v podman >/dev/null 2>&1; then
        (cd "$dir" && podman compose --env-file .env "$@")
    else
        echo "termix: docker or podman is required for the internal Caddy edge" >&2
        return 1
    fi
}

termix_caddy_up() {
    local dir network
    dir="$(termix_caddy_dir)"
    network="$(termix_caddy_network)"
    termix_need_cmd python3
    if ! podman network inspect "$network" >/dev/null 2>&1 && \
       ! docker network inspect "$network" >/dev/null 2>&1; then
        echo "termix: Termix compose network ${network} is missing; start Termix first" >&2
        return 1
    fi
    echo "termix: starting internal Caddy edge in ${dir}"
    termix_caddy_compose up -d --build || return $?
    local attempts=30
    while [ "$attempts" -gt 0 ]; do
        if curl -ksS --max-time 3 -o /dev/null -w '%{http_code}' \
            --connect-to termix.krop.ai:8444:127.0.0.1:8444 \
            "https://termix.krop.ai:8444/" | grep -qE '^(200|301|302|304)$'; then
            echo "termix: internal Caddy published $(termix_caddy_url)"
            echo "termix: iPhone Termix app can use that URL, or $(termix_tailnet_url)"
            echo "termix: do not put host.containers.internal in the app"
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 2
    done
    echo "termix: internal Caddy did not become healthy on :8444" >&2
    termix_caddy_compose logs --tail 40 >&2 || true
    return 1
}
