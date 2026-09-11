#!/usr/bin/env bash
# Resolve the local herm-tui fork and keep `herm` pointed at it.
# Sourced by install, install-tui, and myprofile. Safe to exec: writes the shim.
#
# Published npm herm-tui (1.10.0) is never the launch target.

resolve_herm_tui_fork() {
  local c
  for c in \
    "${HERM_TUI_FORK:-}" \
    "${HOME}/src/herm-tui" \
    "${HOME}/src/herm"
  do
    [ -n "$c" ] || continue
    if [ -f "$c/src/index.tsx" ]; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

export_herm_fork_env() {
  local fork
  fork="$(resolve_herm_tui_fork)" || return 1
  export HERM_TUI_FORK="$fork"
  export HERMES_HERM_TUI_DIR="$fork"
  return 0
}

herm_fork_entry() {
  local fork
  fork="$(resolve_herm_tui_fork)" || return 1
  printf '%s\n' "$fork/src/index.tsx"
}

write_herm_fork_shim() {
  local fork entry shim tmp
  local toolchain="${HERMES_TOOLCHAIN_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/hermes-toolchain}"
  local bun_home="${HERMES_BUN_HOME:-$toolchain/bun}"
  local pnpm_home="${HERMES_PNPM_HOME:-$toolchain/pnpm}"
  local venv="${HERMES_PYTHON_VENV:-$toolchain/venv}"
  local shim_dir="${HERMES_SHIM_DIR:-$HOME/.local/bin}"
  local bun="$bun_home/bin/bun"

  fork="$(resolve_herm_tui_fork)" || {
    echo "ERROR: herm-tui fork not found (expected ~/src/herm-tui or ~/src/herm)" >&2
    return 1
  }
  entry="$fork/src/index.tsx"
  [ -f "$entry" ] || {
    echo "ERROR: herm-tui entry missing: $entry" >&2
    return 1
  }
  mkdir -p "$shim_dir"
  shim="$shim_dir/herm"
  tmp="$(mktemp "$shim_dir/.herm.XXXXXX")"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'export HERMES_TOOLCHAIN_HOME=%q\n' "$toolchain"
    printf 'export HERM_TUI_FORK=%q\n' "$fork"
    printf 'export HERMES_HERM_TUI_DIR=%q\n' "$fork"
    printf 'export PNPM_HOME=%q\n' "$pnpm_home"
    printf 'export PATH=%q:%q:%q:"$PATH"\n' "$bun_home/bin" "$pnpm_home/bin" "$venv/bin"
    printf 'if [ -f %q ]; then\n' "$HOME/src/profile/bin/hermes/fork-env.sh"
    printf '  # timeout-free cursor-sdk overlay (required for provider=cursor)\n'
    printf '  . %q\n' "$HOME/src/profile/bin/hermes/fork-env.sh"
    printf 'fi\n'
    printf 'if [ ! -x %q ]; then\n' "$bun"
    printf '  echo "ERROR: bun missing at %s; run bin/hermes/install-tui" >&2\n' "$bun"
    printf '  exit 127\n'
    printf 'fi\n'
    printf 'exec %q %q "$@"\n' "$bun" "$entry"
  } > "$tmp"
  chmod 0755 "$tmp"
  mv -f "$tmp" "$shim"
}

herm_fork_ensure_shim() {
  local fork entry shim
  fork="$(resolve_herm_tui_fork)" || return 0
  entry="$fork/src/index.tsx"
  shim="${HERMES_SHIM_DIR:-$HOME/.local/bin}/herm"
  if [ -x "$shim" ] && grep -Fq "$entry" "$shim" 2>/dev/null; then
    return 0
  fi
  write_herm_fork_shim
}

if [ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  export_herm_fork_env
  write_herm_fork_shim
  printf 'herm_fork=%s\n' "$HERM_TUI_FORK"
  printf 'herm_shim=%s\n' "${HERMES_SHIM_DIR:-$HOME/.local/bin}/herm"
fi
