#!/usr/bin/env bash
# Detect personal vs work host class and export class-gated Hermes paths.
# Source this file, or run: host-env.sh --class|--export|--help
#
# Overrides:
#   AGENTIC_HOST_CLASS=personal|work
#   PROFILE_ENV=personal|work
#   AGENTIC_HOSTNAME=...          (tests)
#   AGENTIC_KH_DIR=...            (tests; default ~/src/karan.hiremath)
#
# Distinct registries:
#   personal — ~/src/hermes only (krop-tf / krop-infra / krop-ai). Never KH.
#   work     — ~/src/karan.hiremath agentic Hermes first. No krop registry.
# Do not `set -e` when sourced — that would leak into the operator shell.

_agentic_host_env_script="${BASH_SOURCE[0]:-$0}"
while [ -L "$_agentic_host_env_script" ]; do
  _agentic_dir="$(cd -P "$(dirname "$_agentic_host_env_script")" && pwd)"
  _agentic_host_env_script="$(readlink "$_agentic_host_env_script")"
  case "$_agentic_host_env_script" in
    /*) ;;
    *) _agentic_host_env_script="$_agentic_dir/$_agentic_host_env_script" ;;
  esac
done
AGENTIC_DEV_DIR="$(cd -P "$(dirname "$_agentic_host_env_script")" && pwd)"
unset _agentic_host_env_script _agentic_dir

_agentic_usage() {
  cat <<'EOF'
Usage: host-env.sh [--class|--export|--help]

  --class    print personal|work
  --export   print eval-able export lines
  (source)   apply exports in the current shell

Overrides: AGENTIC_HOST_CLASS, PROFILE_ENV, AGENTIC_HOSTNAME, AGENTIC_KH_DIR
EOF
}

_agentic_detect_class() {
  local override hn kh uname_s
  override="${AGENTIC_HOST_CLASS:-${PROFILE_ENV:-}}"
  case "$override" in
    personal|work) printf '%s\n' "$override"; return 0 ;;
    "" ) ;;
    *)
      echo "host-env: invalid AGENTIC_HOST_CLASS/PROFILE_ENV: $override" >&2
      return 2
      ;;
  esac

  hn="${AGENTIC_HOSTNAME:-$(hostname -s 2>/dev/null || uname -n)}"
  hn="${hn%%.*}"
  kh="${AGENTIC_KH_DIR:-$HOME/src/karan.hiremath}"
  uname_s="$(uname -s)"

  case "$hn" in
    khire-mac-mini|home-mac-mini|home-mbp-13) printf 'personal\n'; return 0 ;;
    cxis-devlarge-2|tc2) printf 'work\n'; return 0 ;;
    karans-macbook-pro*|karans-mbp*) printf 'work\n'; return 0 ;;
  esac

  if [ "$uname_s" = Darwin ] && [ ! -d "$kh" ]; then
    printf 'personal\n'
    return 0
  fi
  if [ -d "$kh" ]; then
    printf 'work\n'
    return 0
  fi
  printf 'personal\n'
}

_agentic_apply() {
  local class profile_root hermes_profiles kh_profiles tool_profiles
  local hermes_projects kh_projects tool_projects
  class="$(_agentic_detect_class)"
  AGENTIC_HOST_CLASS="$class"

  profile_root="${PROFILE_DIR:-$HOME/src/profile}"
  hermes_profiles="$HOME/src/hermes/profiles"
  kh_profiles="$HOME/src/karan.hiremath/agentic/hermes/profiles"
  tool_profiles="$profile_root/bin/hermes/profiles"
  hermes_projects="$HOME/src/hermes/projects"
  kh_projects="$HOME/src/karan.hiremath/agentic/hermes/projects"
  tool_projects="$profile_root/bin/hermes/projects"

  if [ "$class" = personal ]; then
    # Never search the work checkout, even if it was cloned by mistake.
    HERMES_AGENT_PROFILE_PATH="${HERMES_AGENT_PROFILE_PATH:-${hermes_profiles}:${tool_profiles}}"
    HERMES_PROJECT_REGISTRY_PATH="${HERMES_PROJECT_REGISTRY_PATH:-${hermes_projects}:${tool_projects}}"
    AGENTIC_COSW_PLANE=krop
  else
    # Work CosW is KH-first. Personal CoS YAML can still resolve from hermes.
    # Project registry stays work-only so `pm` does not see krop-* on a work host.
    HERMES_AGENT_PROFILE_PATH="${HERMES_AGENT_PROFILE_PATH:-${kh_profiles}:${hermes_profiles}:${tool_profiles}}"
    HERMES_PROJECT_REGISTRY_PATH="${HERMES_PROJECT_REGISTRY_PATH:-${kh_projects}:${tool_projects}}"
    AGENTIC_COSW_PLANE=work
  fi

  export AGENTIC_HOST_CLASS
  export HERMES_AGENT_PROFILE_PATH
  export HERMES_PROJECT_REGISTRY_PATH
  export HERMES_PROJECT_REGISTRY_DIRS="$HERMES_PROJECT_REGISTRY_PATH"
  export AGENTIC_COSW_PLANE
}

_agentic_print_exports() {
  _agentic_apply
  printf 'export AGENTIC_HOST_CLASS=%q\n' "$AGENTIC_HOST_CLASS"
  printf 'export HERMES_AGENT_PROFILE_PATH=%q\n' "$HERMES_AGENT_PROFILE_PATH"
  printf 'export HERMES_PROJECT_REGISTRY_PATH=%q\n' "$HERMES_PROJECT_REGISTRY_PATH"
  printf 'export HERMES_PROJECT_REGISTRY_DIRS=%q\n' "$HERMES_PROJECT_REGISTRY_DIRS"
  printf 'export AGENTIC_COSW_PLANE=%q\n' "$AGENTIC_COSW_PLANE"
}

_agentic_print_json() {
  _agentic_apply
  python3 -c '
import json, os
print(json.dumps({
    "class": os.environ["AGENTIC_HOST_CLASS"],
    "plane": os.environ["AGENTIC_COSW_PLANE"],
    "HERMES_AGENT_PROFILE_PATH": os.environ["HERMES_AGENT_PROFILE_PATH"],
    "HERMES_PROJECT_REGISTRY_PATH": os.environ["HERMES_PROJECT_REGISTRY_PATH"],
}))
'
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  case "${1:-}" in
    --help|-h|help) _agentic_usage ;;
    --export) _agentic_print_exports ;;
    --json) _agentic_apply; _agentic_print_json ;;
    --class|class|"") _agentic_apply; printf '%s\n' "$AGENTIC_HOST_CLASS" ;;
    *)
      echo "host-env: unknown argument: $1" >&2
      _agentic_usage >&2
      exit 2
      ;;
  esac
else
  _agentic_apply
fi
