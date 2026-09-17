#!/usr/bin/env bash
set -euo pipefail

export HWORK_INSIDE_CONTAINER=1
export HOME="${HOME:-/hwork-home}"
export PROFILE_REAL_HOME="/workspace"
export PROFILE_DIR="/workspace/src/profile"
export HERMES_PROFILE="${HERMES_PROFILE:-hwork}"
export HERMES_SANDBOX_PROFILE="${HERMES_SANDBOX_PROFILE:-hwork}"
export HERMES_HOME="${HERMES_HOME:-/hwork-profile}"
export HERMES_TOOLCHAIN="${HERMES_TOOLCHAIN:-/usr/local}"
export PATH="/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"
export MACHINE="hwork-sandbox"
export TERMINAL_ENV="${TERMINAL_ENV:-local}"
export TERM="${TERM:-xterm-256color}"

mkdir -p "$HOME" "$HERMES_HOME" "$HOME/.config/herdr"
cd /workspace/src/karan.hiremath

status() {
  cat <<EOF
hwork_container_status:
  hostname: $(hostname)
  uname: $(uname -a)
  pwd: $(pwd)
  HOME: ${HOME}
  HERMES_HOME: ${HERMES_HOME}
  HERMES_PROFILE: ${HERMES_PROFILE}
  herdr: $(command -v herdr || true)
  herm: $(command -v herm || true)
  hermes: $(command -v hermes || true)
  tmux: $(command -v tmux || true)
EOF
}

case "${1:-cockpit}" in
  --status|status) status; exit 0 ;;
  --shell|shell) exec "${SHELL:-/bin/bash}" -l ;;
  --agent|agent|--hermes) exec hermes -p hwork ;;
  --herm|herm) exec herm ;;
  --help|-h|help)
    cat <<'EOF'
Usage: hwork container entrypoint [status|shell|agent|herm]
Default launches tmux cockpit with herdr + herm.
EOF
    exit 0
    ;;
esac

session="${HWORK_TMUX_SESSION:-hwork}"
if ! tmux has-session -t "$session" 2>/dev/null; then
  tmux new-session -d -s "$session" -n herdr -c /workspace/src/karan.hiremath 'exec herdr --session hwork'
  tmux new-window -t "$session:" -n herm -c /workspace/src/karan.hiremath 'exec herm'
  tmux new-window -t "$session:" -n lanes -c /workspace/src/karan.hiremath "printf '%s\n' 'hwork sandbox container' 'hostname:' \"$(hostname)\" '' 'lanes on host entrypoint:' '  hwork control' '  hwork bifrost' '  hwork training' '  hwork security'; exec bash -l"
  tmux select-window -t "$session:herdr"
fi
exec tmux attach-session -t "$session"
