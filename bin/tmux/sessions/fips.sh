#!/bin/bash
# tmux session layout: fips
# Description: FIPS build workspace on Crusoe cluster
#   Window 1: bifrost-fips repo (build commands)
#   Window 2: gypsum repo (dependency reference)
#   Window 3: build logs (tail)
#   Window 4: slurm (squeue, sinfo)

set -euo pipefail

SESSION_NAME="${1:-fips}"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists. Attaching..."
    if [ -n "${TMUX:-}" ]; then
        tmux switch-client -t "$SESSION_NAME"
    else
        tmux attach-session -t "$SESSION_NAME"
    fi
    exit 0
fi

tmux new-session -d -s "$SESSION_NAME" -n "bifrost" -c "$HOME/bifrost-fips"
tmux send-keys -t "$SESSION_NAME:bifrost" "git log --oneline -5 && echo '---' && echo 'just fips-build-gypsum | fips-build-all | fips-build-slurm cx-1'" C-m

tmux new-window -t "$SESSION_NAME" -n "gypsum" -c "$HOME/gypsum"

tmux new-window -t "$SESSION_NAME" -n "logs" -c "$HOME"
tmux send-keys -t "$SESSION_NAME:logs" "ls -t ~/fips-*.log 2>/dev/null | head -1 | xargs tail -f 2>/dev/null || echo 'No build logs yet'" C-m

tmux new-window -t "$SESSION_NAME" -n "slurm" -c "$HOME"
tmux send-keys -t "$SESSION_NAME:slurm" "squeue -u \$USER && echo '---' && sinfo -p interactive -t idle,mix -o '%n %T %G'" C-m

tmux select-window -t "$SESSION_NAME:bifrost"

if [ -n "${TMUX:-}" ]; then
    tmux switch-client -t "$SESSION_NAME"
else
    tmux attach-session -t "$SESSION_NAME"
fi
