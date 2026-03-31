#!/bin/bash
# tmux session layout: home (remote node dashboard)
# Description: Landing pad when SSHing into a work node.
#   Window 1: dashboard — at-a-glance status of everything running
#   Window 2: scratchpad — empty shell, ready for whatever
#
# Named sessions are for focused work (fips, ops, research).
# This is the "where am I, what's happening" session.

set -euo pipefail

SESSION_NAME="${1:-home}"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    if [ -n "${TMUX:-}" ]; then
        tmux switch-client -t "$SESSION_NAME"
    else
        tmux attach-session -t "$SESSION_NAME"
    fi
    exit 0
fi

# --- Dashboard script (runs in first pane) ---
DASHBOARD=$(cat <<'DASH'
#!/bin/bash
set -euo pipefail

BOLD='\033[1m'; DIM='\033[2m'; GREEN='\033[32m'; YELLOW='\033[33m'; CYAN='\033[36m'; NC='\033[0m'
SEP="${DIM}────────────────────────────────────────────────────${NC}"

echo -e "${BOLD}$(hostname) @ $(date '+%Y-%m-%d %H:%M %Z')${NC}"
echo -e "$SEP"

# tmux sessions
echo -e "${CYAN}▸ tmux sessions${NC}"
tmux list-sessions -F "  #S: #{session_windows} windows #{?session_attached,(attached),}" 2>/dev/null || echo "  (none)"
echo ""

# SLURM queue (if available)
if command -v squeue &>/dev/null; then
    echo -e "${CYAN}▸ slurm jobs${NC}"
    JOBS=$(squeue -u "$USER" -h -o "  %j  %T  %N  %M" 2>/dev/null)
    if [ -n "$JOBS" ]; then
        echo -e "  ${DIM}NAME  STATE  NODE  TIME${NC}"
        echo "$JOBS"
    else
        echo "  (no jobs)"
    fi
    echo ""

    echo -e "${CYAN}▸ gpu nodes${NC}"
    sinfo -p interactive -t idle,mix -h -o "  %n %T %G" 2>/dev/null || echo "  (sinfo unavailable)"
    echo ""
fi

# Docker (if accessible)
if docker ps &>/dev/null 2>&1; then
    echo -e "${CYAN}▸ docker${NC}"
    RUNNING=$(docker ps --format "  {{.Names}}  {{.Status}}" 2>/dev/null | head -5)
    if [ -n "$RUNNING" ]; then echo "$RUNNING"; else echo "  (no containers)"; fi
    echo ""
    echo -e "${CYAN}▸ fips images${NC}"
    docker images --format "  {{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}" 2>/dev/null | grep -i fips | head -10 || echo "  (none)"
    echo ""
elif sudo -n docker ps &>/dev/null 2>&1; then
    echo -e "${CYAN}▸ docker (sudo)${NC}"
    sudo -n docker ps --format "  {{.Names}}  {{.Status}}" 2>/dev/null | head -5 || echo "  (no containers)"
    echo ""
else
    echo -e "${CYAN}▸ docker${NC}  ${YELLOW}(no access — not in docker group)${NC}"
    echo ""
fi

# Recent build logs
echo -e "${CYAN}▸ recent build logs${NC}"
ls -t ~/fips-*.log ~/bifrost-*.log 2>/dev/null | head -3 | while read f; do
    SIZE=$(du -h "$f" 2>/dev/null | cut -f1)
    MOD=$(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1)
    LAST=$(tail -1 "$f" 2>/dev/null | head -c 80)
    echo -e "  ${DIM}${f##*/}${NC} (${SIZE}, ${MOD})"
    echo -e "  └─ ${LAST}"
done
[ -z "$(ls ~/fips-*.log ~/bifrost-*.log 2>/dev/null)" ] && echo "  (none)"
echo ""

# Git repos
echo -e "${CYAN}▸ repos${NC}"
for d in ~/bifrost-fips ~/gypsum ~/compliance; do
    if [ -d "$d/.git" ]; then
        BRANCH=$(cd "$d" && git branch --show-current 2>/dev/null)
        COMMIT=$(cd "$d" && git log -1 --format='%h %s' 2>/dev/null | head -c 60)
        echo -e "  ${BOLD}${d##*/}${NC} (${GREEN}${BRANCH}${NC}) ${DIM}${COMMIT}${NC}"
    fi
done
echo ""

# Disk
echo -e "${CYAN}▸ disk${NC}"
df -h /home /scratch /data_vast 2>/dev/null | awk 'NR==1{printf "  %-20s %6s %6s %5s\n","MOUNT","SIZE","USED","USE%"} NR>1{printf "  %-20s %6s %6s %5s\n",$6,$2,$3,$5}'
echo ""
echo -e "$SEP"
echo -e "${DIM}tc cxis-devlarge fips  │  tc cxis-devlarge ops  │  tmux ls${NC}"
DASH
)

# Create session with dashboard window
tmux new-session -d -s "$SESSION_NAME" -n "dashboard" -c "$HOME"
tmux send-keys -t "$SESSION_NAME:dashboard" "bash -c $(printf '%q' "$DASHBOARD")" C-m

# btop window
tmux new-window -t "$SESSION_NAME" -n "btop" -c "$HOME"
tmux send-keys -t "$SESSION_NAME:btop" "btop 2>/dev/null || ~/.local/bin/btop 2>/dev/null || htop" C-m

# Scratchpad window
tmux new-window -t "$SESSION_NAME" -n "scratch" -c "$HOME"

tmux select-window -t "$SESSION_NAME:dashboard"

if [ -n "${TMUX:-}" ]; then
    tmux switch-client -t "$SESSION_NAME"
else
    tmux attach-session -t "$SESSION_NAME"
fi
