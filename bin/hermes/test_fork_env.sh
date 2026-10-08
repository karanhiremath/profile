#!/usr/bin/env bash
# fork-env must pin HERMES_AGENT_ROOT to the timeout-free overlay so herm's
# gateway does not prepend ~/.hermes/hermes-agent and drop Cursor.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

unset HERMES_AGENT_ROOT HERMES_AGENT_FORK_ROOT HERMES_PYTHON
# shellcheck source=fork-env.sh
. "$DIR/fork-env.sh"

[ -n "${HERMES_AGENT_ROOT:-}" ] || fail "HERMES_AGENT_ROOT unset"
[ "$HERMES_AGENT_ROOT" = "${HERMES_AGENT_FORK_ROOT:-}" ] || fail "FORK_ROOT mismatch"
if [ -x "${HERMES_TOOLCHAIN_HOME:-$HOME/.local/share/hermes-toolchain}/venv/bin/python" ]; then
  [ -n "${HERMES_PYTHON:-}" ] || fail "HERMES_PYTHON unset"
fi
[ -f "$HERMES_AGENT_ROOT/plugins/model-providers/cursor/__init__.py" ] || fail "cursor plugin missing under HERMES_AGENT_ROOT"
grep -q '_operator_run_timeout_seconds' "$HERMES_AGENT_ROOT/agent/cursor_sdk_client.py" || fail "HERMES_AGENT_ROOT is not the timeout-free overlay"

case ":${PYTHONPATH:-}:" in
  *":${HERMES_AGENT_ROOT}:"*) ;;
  *) fail "PYTHONPATH missing overlay" ;;
esac

PY="${HERMES_PYTHON:-${HERMES_TOOLCHAIN_HOME:-$HOME/.local/share/hermes-toolchain}/venv/bin/python}"
[ -x "$PY" ] || fail "toolchain python missing: $PY"

overlay_probe="$("$PY" - <<'PY'
import os
from hermes_cli.auth import PROVIDER_REGISTRY
from providers import get_provider_profile
print("cursor_profile", "yes" if get_provider_profile("cursor") else "no")
print("cursor_registry", "yes" if "cursor" in PROVIDER_REGISTRY else "no")
print("root", os.environ.get("HERMES_AGENT_ROOT", ""))
PY
)"
printf '%s\n' "$overlay_probe" | grep -q 'cursor_profile yes' || fail "overlay missing cursor profile: $overlay_probe"
printf '%s\n' "$overlay_probe" | grep -q 'cursor_registry yes' || fail "overlay missing cursor registry: $overlay_probe"

printf 'ok HERMES_AGENT_ROOT=%s\n' "$HERMES_AGENT_ROOT"
