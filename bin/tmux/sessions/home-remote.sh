#!/bin/bash
# tmux session layout: home (remote node dashboard)
# Description: Landing pad when SSHing into a work node.
#   Window 1: dashboard — at-a-glance status
#   Window 2: btop — system monitor
#   Window 3: scratch — empty shell

set -euo pipefail

SESSION_NAME="${1:-home}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_SCRIPT="${SCRIPT_DIR}/dashboard.sh"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    if [ -n "${TMUX:-}" ]; then
        tmux switch-client -t "$SESSION_NAME"
    else
        tmux attach-session -t "$SESSION_NAME"
    fi
    exit 0
fi

tmux new-session -d -s "$SESSION_NAME" -n "dashboard" -c "$HOME"
if [ -x "$DASHBOARD_SCRIPT" ]; then
    tmux send-keys -t "$SESSION_NAME:dashboard" "$DASHBOARD_SCRIPT" C-m
else
    tmux send-keys -t "$SESSION_NAME:dashboard" "echo 'dashboard.sh not found'" C-m
fi

tmux new-window -t "$SESSION_NAME" -n "btop" -c "$HOME"
tmux send-keys -t "$SESSION_NAME:btop" "btop 2>/dev/null || ~/.local/bin/btop 2>/dev/null || htop" C-m

tmux new-window -t "$SESSION_NAME" -n "scratch" -c "$HOME"

tmux select-window -t "$SESSION_NAME:dashboard"

if [ -n "${TMUX:-}" ]; then
    tmux switch-client -t "$SESSION_NAME"
else
    tmux attach-session -t "$SESSION_NAME"
fi
