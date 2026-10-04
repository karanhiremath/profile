#!/usr/bin/env bash
# Provision Tailscale Serve for the local Termix endpoint. Never enables Funnel.

if [ -z "${TERMIX_LIB_DIR:-}" ]; then
    TERMIX_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
# shellcheck source=common.sh
. "${TERMIX_LIB_DIR}/common.sh"

termix_serve_summarize() {
    local desired port
    desired="$(termix_desired_proxy)"
    port="$(termix_serve_https_port)"
    tailscale serve status --json 2>/dev/null | python3 "${TERMIX_LIB_DIR}/serve_status.py" "$desired" "$port"
}

termix_serve_apply() {
    local desired="$1"
    local tmp pid elapsed timeout_s line enable_url
    timeout_s="${TERMIX_SERVE_TIMEOUT:-12}"
    tmp="$(mktemp)"
    tailscale serve --bg --yes --https="$(termix_serve_https_port)" "$desired" >"$tmp" 2>&1 &
    pid=$!
    elapsed=0
    while kill -0 "$pid" 2>/dev/null; do
        if grep -q 'Serve is not enabled' "$tmp"; then
            enable_url="$(grep -Eo 'https://login\.tailscale\.com/[^[:space:]]+' "$tmp" | head -1 || true)"
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            echo "termix: Tailscale Serve is not enabled on this tailnet" >&2
            if [ -n "$enable_url" ]; then
                echo "termix: enable it at ${enable_url} then rerun termix-up serve" >&2
            fi
            rm -f "$tmp"
            return 2
        fi
        if [ "$elapsed" -ge "$timeout_s" ]; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            echo "termix: timed out waiting for Tailscale Serve" >&2
            cat "$tmp" >&2 || true
            rm -f "$tmp"
            return 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    wait "$pid"
    local rc=$?
    if [ "$rc" -ne 0 ]; then
        cat "$tmp" >&2 || true
        rm -f "$tmp"
        return "$rc"
    fi
    while IFS= read -r line; do
        [ -n "$line" ] && echo "$line"
    done < "$tmp"
    rm -f "$tmp"
    return 0
}

termix_serve_provision() {
    local desired summary empty matches proxy_matches funnel https_port
    termix_need_cmd tailscale
    termix_need_cmd python3
    desired="$(termix_desired_proxy)"
    https_port="$(termix_serve_https_port)"

    if ! tailscale status >/dev/null 2>&1; then
        echo "termix: Tailscale is not running" >&2
        return 1
    fi

    summary="$(termix_serve_summarize)"
    empty="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["empty"])' "$summary")"
    matches="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["matches"])' "$summary")"
    proxy_matches="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("proxy_matches"))' "$summary")"
    funnel="$(python3 -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])["funnel"]))' "$summary")"

    if [ -n "$funnel" ]; then
        echo "termix: refusing to keep Tailscale Funnel enabled for ${funnel}" >&2
        echo "termix: Termix stays tailnet-only; Funnel must stay off" >&2
        return 1
    fi

    if [ "$matches" = "True" ]; then
        echo "termix: Tailscale Serve already proxies ${desired} on :${https_port}"
        return 0
    fi

    if [ "$proxy_matches" = "True" ]; then
        echo "termix: adding Tailscale Serve HTTPS :${https_port} without resetting existing handlers"
        termix_serve_apply "$desired" || return $?
        summary="$(termix_serve_summarize)"
        matches="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["matches"])' "$summary")"
        funnel="$(python3 -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])["funnel"]))' "$summary")"
        if [ "$matches" = "True" ] && [ -z "$funnel" ]; then
            echo "termix: Tailscale Serve published ${desired} at $(termix_tailnet_url)"
            return 0
        fi
        echo "termix: failed to add Serve HTTPS :${https_port}" >&2
        echo "$summary" >&2
        return 1
    fi

    if [ "$empty" != "True" ] && [ "${TERMIX_SERVE_FORCE:-0}" != "1" ]; then
        echo "termix: existing Tailscale Serve config does not match ${desired}" >&2
        echo "$summary" >&2
        echo "termix: set TERMIX_SERVE_FORCE=1 to replace it" >&2
        return 1
    fi

    if [ "$empty" != "True" ]; then
        echo "termix: replacing Tailscale Serve config (TERMIX_SERVE_FORCE=1)"
        tailscale serve reset
    fi

    # HTTPS on this node's MagicDNS name, tailnet-only. Do not use `funnel`.
    # `tailscale serve` waits on a login URL when the tailnet has Serve disabled.
    termix_serve_apply "$desired" || return $?

    summary="$(termix_serve_summarize)"
    matches="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["matches"])' "$summary")"
    funnel="$(python3 -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])["funnel"]))' "$summary")"
    if [ "$matches" != "True" ]; then
        echo "termix: Tailscale Serve did not publish ${desired}" >&2
        echo "$summary" >&2
        return 1
    fi
    if [ -n "$funnel" ]; then
        echo "termix: Serve unexpectedly enabled Funnel: ${funnel}" >&2
        return 1
    fi
    echo "termix: Tailscale Serve published ${desired} at $(termix_tailnet_url)"
}
