#!/usr/bin/env bash
# Multiple herm-tui panes per HERMES_HOME.
# Each pane owns its own tui_gateway stdin pipe and Hermes session.
# Coordinate via atop_vi buffers — never by sharing a rendered TUI.
#
# Sourced by `agents up`. Also usable as:
#   . tui-panes.sh && tui_panes_live "$HERMES_HOME"

tui_panes_dir() {
  printf '%s/.herm-tui.panes' "${1:?}"
}

tui_panes_legacy_lock() {
  printf '%s/.herm-tui.lock' "${1:?}"
}

tui_panes_pid_live() {
  local pid="${1:-}"
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  kill -0 "$pid" 2>/dev/null
}

tui_panes_sweep() {
  local home="${1:?}"
  local dir lock pid f
  dir="$(tui_panes_dir "$home")"
  lock="$(tui_panes_legacy_lock "$home")"
  mkdir -p "$dir"
  if [ -f "$lock" ]; then
    pid="$(tr -d '[:space:]' < "$lock" 2>/dev/null || true)"
    if tui_panes_pid_live "$pid"; then
      [ -f "$dir/$pid" ] || printf '%s\n' "$pid" > "$dir/$pid"
    else
      rm -f "$lock"
    fi
  fi
  for f in "$dir"/*; do
    [ -f "$f" ] || continue
    pid="$(basename "$f")"
    if ! tui_panes_pid_live "$pid"; then
      rm -f "$f"
    fi
  done
}

tui_panes_live() {
  local home="${1:?}"
  local dir f pid
  tui_panes_sweep "$home"
  dir="$(tui_panes_dir "$home")"
  for f in "$dir"/*; do
    [ -f "$f" ] || continue
    pid="$(basename "$f")"
    printf '%s\n' "$pid"
  done
}

tui_panes_others() {
  local home="${1:?}"
  local self="${2:-$$}"
  local pid
  for pid in $(tui_panes_live "$home"); do
    [ "$pid" = "$self" ] && continue
    printf '%s\n' "$pid"
  done
}

tui_panes_register() {
  local home="${1:?}"
  local self="${2:-$$}"
  local dir lock
  tui_panes_sweep "$home"
  dir="$(tui_panes_dir "$home")"
  lock="$(tui_panes_legacy_lock "$home")"
  mkdir -p "$dir"
  printf '%s\n' "$self" > "$dir/$self"
  # Compat pointer for old checkers. Not exclusive.
  printf '%s\n' "$self" > "$lock"
}

# Drop -c/--continue/--resume [id] and inject --fresh so an extra pane
# cannot resume the live session (that closes the other pane's gateway pipe).
tui_passthrough_force_fresh() {
  TUI_FRESH_ARGS=(--fresh)
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -c|--continue|--fresh|--new) shift ;;
      --resume)
        shift
        case "${1:-}" in
          ""|-*) ;;
          *) shift ;;
        esac
        ;;
      *) TUI_FRESH_ARGS+=("$1"); shift ;;
    esac
  done
}
