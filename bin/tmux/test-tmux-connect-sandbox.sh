#!/usr/bin/env bash
# Smoke checks for sandbox attach/list command builders.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tmux-connect-sandbox.inc
valid_tmux_ident() { [[ "$1" =~ ^[A-Za-z0-9._:@-]+$ ]]; }
# Minimal stubs so the inc can load without tmux-connect.
get_host_field() { return 1; }
remote_tmux_cmd() { return 1; }
write_sandbox_cache() { cat >/dev/null; }
write_sandbox_session_cache() { cat >/dev/null; }
. "$SCRIPT_DIR/tmux-connect-sandbox.inc"

fail() { echo "FAIL: $*" >&2; exit 1; }

valid_tmux_ident "codex-sandbox" || fail "codex-sandbox should be valid"
valid_tmux_ident "codex-sandbox-hostctl" || fail "codex-sandbox-hostctl should be valid"
valid_tmux_ident "home" || fail "home should be valid"
valid_tmux_ident "bad name" && fail "spaces should be invalid"
valid_tmux_ident 'foo;rm' && fail "metacharacters should be invalid"

cmd="$(sandbox_attach_cmd "codex-sandbox" "home" "cxis-devlarge-2")"
printf '%s\n' "$cmd" | grep -q 'podman exec -it' || fail "attach cmd missing podman exec -it"
printf '%s\n' "$cmd" | grep -q 'new-session -A -s' || fail "attach cmd missing new-session -A"
printf '%s\n' "$cmd" | grep -Fq "'[#S] codex-sandbox @ cxis-devlarge-2 '" || fail "status-left missing sandbox @ host"

cmd="$(sandbox_sessions_cmd "codex-sandbox-hostctl")"
[[ "$cmd" == "podman exec codex-sandbox-hostctl tmux list-sessions" ]] || fail "sessions cmd: $cmd"

echo "ok"
