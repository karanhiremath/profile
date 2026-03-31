#!/bin/bash
# csec ops dashboard — home screen for devlarge
# Pulls: tmux sessions, SLURM, docker, git repos, build logs, GH Pages links
# Refresh: re-run this script or press `r` in the watch loop

set -euo pipefail

BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; CYAN='\033[36m'; BLUE='\033[34m'; MAGENTA='\033[35m'
SEP="${DIM}──────────────────────────────────────────────────────────────────${NC}"
HALF="${DIM}──────────────────────────────${NC}"

header() { echo -e "\n${CYAN}▸ $1${NC}"; }
ok()     { echo -e "  ${GREEN}✓${NC} $1"; }
warn()   { echo -e "  ${YELLOW}⚠${NC} $1"; }
err()    { echo -e "  ${RED}✗${NC} $1"; }
dim()    { echo -e "  ${DIM}$1${NC}"; }
link()   { echo -e "  ${BLUE}↗${NC} ${DIM}$1${NC}"; }

clear
echo -e "${BOLD}┌──────────────────────────────────────────────────────────────┐${NC}"
echo -e "${BOLD}│  csec ops · $(hostname) · $(date '+%Y-%m-%d %H:%M %Z')              │${NC}"
echo -e "${BOLD}└──────────────────────────────────────────────────────────────┘${NC}"

# ── GH Pages dashboards ──
header "dashboards"
link "https://cartesia-ai.github.io/compliance/           cpatch"
link "https://cartesia-ai.github.io/fips-layer-overview/   fips"
link "https://cartesia-ai.github.io/container-scanning/    cscan"
link "https://cartesia-ai.github.io/karan.hiremath/        ops"

# ── tmux sessions ──
header "tmux sessions"
tmux list-sessions -F "  #{session_name}: #{session_windows}w #{?session_attached,${GREEN}(attached)${NC},${DIM}(detached)${NC}}" 2>/dev/null | while read -r line; do
    echo -e "$line"
done
if ! tmux list-sessions &>/dev/null; then dim "(none)"; fi

# ── SLURM ──
if command -v squeue &>/dev/null; then
    header "slurm jobs"
    JOBS=$(squeue -u "$USER" -h -o "%-20j %-8T %-8N %-10M" 2>/dev/null)
    if [ -n "$JOBS" ]; then
        dim "NAME                 STATE    NODE     TIME"
        echo "$JOBS" | while read -r line; do echo "  $line"; done
    else
        dim "(no jobs running)"
    fi

    header "gpu nodes (interactive)"
    sinfo -p interactive -t idle,mix -h -o "  %-8n %-8T %G" 2>/dev/null || dim "(sinfo unavailable)"
fi

# ── Docker / FIPS images ──
header "fips images"
if docker images --format "{{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}" 2>/dev/null | grep -qi fips; then
    docker images --format "  {{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}" 2>/dev/null | grep -i fips | grep -v "none" | head -10
elif sudo -n docker images --format "{{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}" 2>/dev/null | grep -qi fips; then
    sudo -n docker images --format "  {{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}" 2>/dev/null | grep -i fips | grep -v "none" | head -10
else
    dim "(docker: no access on this node — images on cx-* via SLURM)"
fi

# ── Build logs ──
header "recent builds"
LOGS=$(ls -t ~/fips-*.log ~/bifrost-*.log 2>/dev/null | head -3)
if [ -n "$LOGS" ]; then
    echo "$LOGS" | while read -r f; do
        SIZE=$(du -h "$f" 2>/dev/null | cut -f1)
        MOD=$(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1)
        LAST=$(tail -1 "$f" 2>/dev/null | head -c 72)
        echo -e "  ${BOLD}${f##*/}${NC} ${DIM}(${SIZE}, ${MOD})${NC}"
        echo -e "  ${DIM}└─ ${LAST}${NC}"
    done
else
    dim "(no build logs)"
fi

# ── Git repos ──
header "repos"
for d in ~/bifrost-fips ~/gypsum ~/compliance ~/karan.hiremath; do
    if [ -d "$d/.git" ]; then
        NAME=$(basename "$d")
        BRANCH=$(cd "$d" && git branch --show-current 2>/dev/null)
        COMMIT=$(cd "$d" && git log -1 --format='%h %s' 2>/dev/null | head -c 55)
        BEHIND=$(cd "$d" && git rev-list HEAD..@{u} --count 2>/dev/null || echo "?")
        if [ "$BEHIND" = "0" ] || [ "$BEHIND" = "?" ]; then
            echo -e "  ${BOLD}${NAME}${NC} ${GREEN}${BRANCH}${NC} ${DIM}${COMMIT}${NC}"
        else
            echo -e "  ${BOLD}${NAME}${NC} ${YELLOW}${BRANCH} (${BEHIND} behind)${NC} ${DIM}${COMMIT}${NC}"
        fi
    fi
done

# ── Agentic swarm stats ──
header "agentic swarm (karan.hiremath)"
KH_DIR=~/karan.hiremath
if [ -d "$KH_DIR" ]; then
    # Worktrees
    WT_COUNT=$(cd "$KH_DIR" && git worktree list 2>/dev/null | wc -l)
    echo -e "  worktrees: ${BOLD}${WT_COUNT}${NC}"

    # Active projects from memory
    if [ -d "$KH_DIR/agentic/memory/projects" ]; then
        PROJ_COUNT=$(ls "$KH_DIR/agentic/memory/projects/"*.md 2>/dev/null | wc -l)
        PROJS=$(ls "$KH_DIR/agentic/memory/projects/" 2>/dev/null | sed 's/.md$//' | tr '\n' ', ' | sed 's/,$//')
        echo -e "  projects:  ${BOLD}${PROJ_COUNT}${NC} ${DIM}(${PROJS})${NC}"
    fi

    # Daily notes
    LATEST_DAILY=$(ls -t "$KH_DIR/daily/"*.md 2>/dev/null | head -1)
    if [ -n "$LATEST_DAILY" ]; then
        DAILY_DATE=$(basename "$LATEST_DAILY" .md)
        echo -e "  latest daily: ${BOLD}${DAILY_DATE}${NC}"
    fi

    # Skills
    if [ -d "$KH_DIR/agentic/skills" ]; then
        SKILL_COUNT=$(ls -d "$KH_DIR/agentic/skills/"*/SKILL.md 2>/dev/null | wc -l)
        echo -e "  skills: ${BOLD}${SKILL_COUNT}${NC}"
    fi

    # Session index
    if [ -f "$KH_DIR/agentic/memory/SESSION-INDEX.md" ]; then
        ok "SESSION-INDEX.md present"
    else
        warn "SESSION-INDEX.md missing — run checkpoint"
    fi
else
    dim "(karan.hiremath not cloned on this node)"
    dim "git clone git@github.com:cartesia-ai/karan.hiremath.git ~/karan.hiremath"
fi

# ── GitHub auth ──
header "github"
if gh auth status &>/dev/null 2>&1; then
    ok "gh authenticated"
else
    warn "gh auth expired — run: gh auth login"
fi

# ── Disk ──
header "disk"
df -h /home /scratch /data_vast 2>/dev/null | awk '
    NR==1{printf "  %-24s %6s %6s %5s\n","MOUNT","SIZE","USED","USE%"}
    NR>1{
        pct=$5; gsub(/%/,"",pct);
        color="\033[32m"; if(pct+0>80) color="\033[33m"; if(pct+0>95) color="\033[31m";
        printf "  %-24s %6s %6s %s%5s\033[0m\n",$6,$2,$3,color,$5
    }'

echo ""
echo -e "$SEP"
echo -e "${DIM}  tc             │ tc tg            │ tc cxis-devlarge fips${NC}"
echo -e "${DIM}  ic             │ ic staging       │ ic us${NC}"
echo -e "${DIM}  tmux ls        │ squeue           │ dashboard.sh${NC}"
echo -e "$SEP"
