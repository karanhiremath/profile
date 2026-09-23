#!/usr/bin/env bash
# Source from herm/hermes/cosw/agents shims. Pins the timeout-free Cursor
# SDK overlay as both PYTHONPATH and HERMES_AGENT_ROOT.
#
# herm's gateway spawn prepends hermesAgentRoot() — default
# ~/.hermes/hermes-agent — ahead of PYTHONPATH. That stock tree wins and
# drops Cursor from PROVIDER_REGISTRY ("unknown provider cursor"). Pin
# HERMES_AGENT_ROOT so the overlay is the gateway root.
# Safe to source more than once.

# Crusoe SOP: AGENT_SHARED_HOME=/shared/people/$USER. Do not remap $HOME.
# Canonical: karan.hiremath/agentic/infra/crusoe-hermes-homes.md
_kh_agent_shared_env="${HOME}/src/karan.hiremath/agentic/infra/agent-shared-home.env.sh"
_kh_hermes_env="${HOME}/src/karan.hiremath/agentic/infra/crusoe-hermes-home.env.sh"
if [ -f "$_kh_agent_shared_env" ]; then
  # shellcheck disable=SC1090
  . "$_kh_agent_shared_env"
fi
if [ -f "$_kh_hermes_env" ]; then
  # shellcheck disable=SC1090
  . "$_kh_hermes_env"
fi
if [ -z "${AGENT_SHARED_HOME:-}" ] && [ -n "${USER:-}" ] && [ -d "/shared/people/${USER}" ]; then
  export AGENT_SHARED_HOME="/shared/people/${USER}"
fi
if [ -z "${HERMES_AGENTS_DATA_HOME:-}" ] && [ -n "${AGENT_SHARED_HOME:-}" ]; then
  export HERMES_AGENTS_DATA_HOME="${AGENT_SHARED_HOME}/hermes-agents"
  export HERMES_SHARED_PEOPLE_HOME="${HERMES_SHARED_PEOPLE_HOME:-$AGENT_SHARED_HOME}"
  export HERMES_STATE_JOURNAL_MODE="${HERMES_STATE_JOURNAL_MODE:-delete}"
elif [ -z "${HERMES_AGENTS_DATA_HOME:-}" ] && [ -n "${USER:-}" ] && [ -d "/shared/people/${USER}" ]; then
  export HERMES_AGENTS_DATA_HOME="/shared/people/${USER}/hermes-agents"
  export HERMES_SHARED_PEOPLE_HOME="${HERMES_SHARED_PEOPLE_HOME:-/shared/people/${USER}}"
  export HERMES_STATE_JOURNAL_MODE="${HERMES_STATE_JOURNAL_MODE:-delete}"
fi
unset _kh_agent_shared_env _kh_hermes_env

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
  export HERMES_AGENT_ROOT="$overlay"
  unset HERMES_CURSOR_SDK_RUN_TIMEOUT || true
fi
if [ -z "${HERMES_PYTHON:-}" ]; then
  _hermes_py="${HERMES_TOOLCHAIN_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/hermes-toolchain}/venv/bin/python"
  if [ -x "$_hermes_py" ]; then
    export HERMES_PYTHON="$_hermes_py"
  fi
  unset _hermes_py
fi
unset -f _hermes_fork_candidate
