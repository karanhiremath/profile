#!/usr/bin/env bash
# Multi-pane registry: extra Cos panes must not exclusive-lock HERMES_HOME.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

# shellcheck source=tui-panes.sh
. "$DIR/tui-panes.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Dead legacy lock is swept, not fatal.
printf '999999\n' > "$tmp/.herm-tui.lock"
tui_panes_sweep "$tmp"
[ ! -f "$tmp/.herm-tui.lock" ] || fail "dead legacy lock survived sweep"

# Live legacy lock migrates into the pane registry.
printf '%s\n' "$$" > "$tmp/.herm-tui.lock"
tui_panes_sweep "$tmp"
[ -f "$tmp/.herm-tui.panes/$$" ] || fail "live legacy lock did not migrate"

# Register is not exclusive — two live pids coexist.
tui_panes_register "$tmp" "$$"
printf '%s\n' "$$" > "$tmp/.herm-tui.panes/$$"
# Fake a second live pid by copying this shell (we only have one real pid).
# Registry itself must keep both files when both pids are live; use $$ twice
# plus a dead sibling to prove sweep-only-dead.
printf '999998\n' > "$tmp/.herm-tui.panes/999998"
tui_panes_sweep "$tmp"
[ -f "$tmp/.herm-tui.panes/$$" ] || fail "live pane swept"
[ ! -f "$tmp/.herm-tui.panes/999998" ] || fail "dead pane not swept"

live="$(tui_panes_live "$tmp")"
printf '%s\n' "$live" | grep -qx "$$" || fail "live() missing $$"

others="$(tui_panes_others "$tmp" "$$" || true)"
[ -z "$others" ] || fail "others() should be empty when only self is live"

# Force-fresh strips resume flags so extra panes do not steal the pipe.
tui_passthrough_force_fresh -c --foo --resume abc123 --bar
[ "${TUI_FRESH_ARGS[0]}" = "--fresh" ] || fail "missing --fresh"
printf '%s\n' "${TUI_FRESH_ARGS[@]}" | grep -qx -- --foo || fail "kept --foo"
printf '%s\n' "${TUI_FRESH_ARGS[@]}" | grep -qx -- --bar || fail "kept --bar"
printf '%s\n' "${TUI_FRESH_ARGS[@]}" | grep -qx -- -c && fail "kept -c"
printf '%s\n' "${TUI_FRESH_ARGS[@]}" | grep -qx -- --resume && fail "kept --resume"
printf '%s\n' "${TUI_FRESH_ARGS[@]}" | grep -qx -- abc123 && fail "kept resume id"

# Launcher no longer dies on a live TUI.
grep -q 'One Cos pane per home' "$DIR/agents" && fail "exclusive lock still in agents"
grep -q 'tui-panes.sh' "$DIR/agents" || fail "agents does not source tui-panes.sh"

echo "ok"
