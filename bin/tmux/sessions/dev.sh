#!/bin/bash
# tmux session layout: dev
# Description: Development workspace with editor, terminal, and server windows

set -euo pipefail

SESSION_NAME="${1:-dev}"

# If session already exists, just attach
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists. Attaching..."
    if [ -n "${TMUX:-}" ]; then
        tmux switch-client -t "$SESSION_NAME"
    else
        tmux attach-session -t "$SESSION_NAME"
    fi
    exit 0
fi

# Create session with editor window
tmux new-session -d -s "$SESSION_NAME" -n "editor" -c "$HOME/src"
tmux send-keys -t "$SESSION_NAME:editor" "nvim" C-m

# Terminal window with horizontal split
tmux new-window -t "$SESSION_NAME" -n "terminal" -c "$HOME/src"
tmux split-window -h -t "$SESSION_NAME:terminal" -c "$HOME/src"

# Server/logs window
tmux new-window -t "$SESSION_NAME" -n "server" -c "$HOME/src"

# Select the first window
tmux select-window -t "$SESSION_NAME:editor"

# Attach
if [ -n "${TMUX:-}" ]; then
    tmux switch-client -t "$SESSION_NAME"
else
    tmux attach-session -t "$SESSION_NAME"
fi
