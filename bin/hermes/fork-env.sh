#!/usr/bin/env bash
# Source from herm/hermes/cosw/agents shims. Exports PYTHONPATH to the
# karanhiremath/hermes-agent fork overlay (timeout-free Cursor SDK).
# Safe to source more than once.

_hermes_fork_candidate() {
  local candidate file
  for candidate in \
    "${COSW_TIMEOUT_FREE_PYTHONPATH:-}" \
    "${HERMES_AGENT_OVERLAY:-}" \
    "${HOME}/src/hermes-agent-worktrees/timeout-free-cursor-sdk" \
    "${HOME}/src/hermes-agent-worktrees/timeout-free-cursor-sdk-20260831T1834" \
    "${HERMES_AGENT_FORK:-${HOME}/src/hermes-agent}"
  do
    [ -n "$candidate" ] || continue
    file="$candidate/agent/cursor_sdk_client.py"
    if [ -f "$file" ] && grep -q '_operator_run_timeout_seconds' "$file"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if overlay="$(_hermes_fork_candidate)"; then
  case ":${PYTHONPATH:-}:" in
    *":${overlay}:"*) ;;
    *) export PYTHONPATH="${overlay}${PYTHONPATH:+:$PYTHONPATH}" ;;
  esac
  export HERMES_AGENT_FORK_ROOT="$overlay"
  unset HERMES_CURSOR_SDK_RUN_TIMEOUT || true
fi
unset -f _hermes_fork_candidate
