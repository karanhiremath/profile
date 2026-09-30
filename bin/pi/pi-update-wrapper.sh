# pi-update-wrapper.sh — sourced by ~/.zshrc / ~/.bashrc / ~/.bash_profile.
#
# Canonical source: <profile>/bin/pi/pi-update-wrapper.sh
# Installed by bin/pi/install and bin/zsh/install to:
#   ~/.pi/agent/bin/pi-update-wrapper.sh
#
# Defines a `pi` shell function that checks for and applies updates to BOTH the
# pi core harness and all installed extensions/packages (native
# `pi update --all`) before launching a NEW interactive pi session.
#
# Pre-update is SKIPPED for:
#   - explicit subcommands: update/install/remove/uninstall/list/config/auth/export
#     (`pi update ...` IS the update; do not double-run it)
#   - non-session invocations: -p/--print, -v/--version, -h/--help, --offline,
#     --export, session reuse: -c/--continue, -r/--resume, --session, --fork
#   - PI_NO_UPDATE=1 (escape hatch for debugging / offline work)
#
# Knobs:
#   PI_NO_UPDATE=1        skip the pre-launch update entirely
#   PI_UPDATE_TIMEOUT=120 seconds allowed for `pi update --all` (default 120)
#
# Failure semantics: if the update fails or times out, launch the existing
# install anyway (warning on stderr). Never block a launch on the updater.
#
# Binary resolution: hosts differ. tc2 keeps a profile-managed grant wrapper
# at ~/.local/bin/pi; hosts without it (e.g. pnpm-global installs) fall back
# to the pnpm global bin dir. Resolution must never match this function.
_pi_resolve() {
  local _cand
  for _cand in \
    "$HOME/.local/bin/pi" \
    "$HOME/.pi/agent/bin/pi" \
    "${PNPM_HOME:-$HOME/.local/share/pnpm}/bin/pi" \
    "$HOME/.local/share/pnpm/bin/pi"
  do
    [ -x "$_cand" ] && { printf '%s\n' "$_cand"; return 0; }
  done
  return 1
}

pi() {
  local _pi_real
  _pi_real="$(_pi_resolve)" || {
    echo "[pi] ERROR: pi binary not found (checked ~/.local/bin/pi, ~/.pi/agent/bin/pi, pnpm bin)" >&2
    return 127
  }

  # Explicit subcommands: run as-is.
  case "$1" in
    update|install|remove|uninstall|list|config|auth|export)
      "$_pi_real" "$@"
      return $?
      ;;
  esac

  # Scan flags for non-session invocations; `--` ends option scanning.
  local arg skip=0
  for arg in "$@"; do
    case "$arg" in
      --) break ;;
      -p|--print|-v|--version|-h|--help|--offline|--export|-c|--continue|-r|--resume|--session|--session=*|--fork|--fork=*) skip=1; break ;;
    esac
  done

  if [ "$skip" -eq 0 ] && [ "${PI_NO_UPDATE:-0}" != "1" ]; then
    echo "[pi] update check: core harness + extensions ..."
    if command -v timeout >/dev/null 2>&1; then
      timeout "${PI_UPDATE_TIMEOUT:-120}" "$_pi_real" update --all
    else
      "$_pi_real" update --all
    fi
    local _rc=$?
    if [ "$_rc" -ne 0 ]; then
      echo "[pi] WARNING: pre-launch update failed (rc=$_rc); launching existing install." >&2
    fi
  fi

  # Re-resolve after the update: self-update may rewrite the shim to a new release.
  _pi_real="$(_pi_resolve)" || return 127
  "$_pi_real" "$@"
}