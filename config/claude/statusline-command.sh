#!/usr/bin/env bash
# Claude Code status line — mirrors zsh PROMPT style
#
# Line 1: datetime | user@host | path
# Line 2: (branch) | model | ctx

input=$(cat) || input=""

cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // ""' 2>/dev/null) || cwd=""
model=$(echo "$input" | jq -r '.model.display_name // ""' 2>/dev/null) || model=""
remaining=$(echo "$input" | jq -r '.context_window.remaining_percentage // empty' 2>/dev/null) || remaining=""

# Shorten home directory to ~
home="$HOME"
short_cwd="${cwd/#$home/~}"
[ -z "$short_cwd" ] && short_cwd="~"

timestamp=$(date "+%Y-%m-%d %H:%M:%S")
user=$(whoami 2>/dev/null || echo "")
host=$(hostname -s 2>/dev/null || echo "")

# Git branch (skip all locks, fail gracefully)
branch=""
branch_dirty=0
if [ -n "$cwd" ] && git -C "$cwd" rev-parse --git-dir --no-optional-locks >/dev/null 2>&1; then
  branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
    || git -C "$cwd" rev-parse --short HEAD 2>/dev/null \
    || echo "")
  if git -C "$cwd" status --porcelain --no-optional-locks 2>/dev/null | grep -q .; then
    branch_dirty=1
  fi
fi

# Context percentage. The JSON field is remaining (FREE) context; print USED so
# the compaction thresholds (60% used = prepare, 75-80% used = hand off) are
# read directly off the statusline instead of being inverted by mistake.
ctx_str=""
ctx_used=""
if [ -n "$remaining" ]; then
  ctx_used=$(awk -v r="$remaining" 'BEGIN { u = 100 - r; if (u < 0) u = 0; printf "%.0f", u }')
  ctx_str="ctx: ${ctx_used}% used"
fi

# Colors (bright variants to show through dimming)
RED=$'\033[0;91m'
GREEN=$'\033[0;92m'
YELLOW=$'\033[0;93m'
BLUE=$'\033[0;94m'
CYAN=$'\033[0;96m'
RESET=$'\033[0m'
SEP=" ${YELLOW}|${RESET} "

# ===== LINE 1: datetime | user@host | path =====
printf '%s' "${RED}${timestamp}${RESET}${SEP}${CYAN}${user}${RED}@${host}${RESET}${SEP}${RED}${short_cwd}${RESET}"
printf '\n'

# ===== LINE 2: (branch) | model | ctx =====
l2=""
if [ -n "$branch" ]; then
  if [ "$branch_dirty" -eq 1 ]; then
    branch_color="$RED"
  else
    branch_color="$GREEN"
  fi
  l2="${RED}(${RESET}${branch_color}${branch}${RESET}${RED})${RESET}"
fi
if [ -n "$model" ]; then
  [ -n "$l2" ] && l2+="$SEP"
  l2+="${BLUE}${model}${RESET}"
fi
if [ -n "$ctx_str" ]; then
  [ -n "$l2" ] && l2+="$SEP"
  # green = plenty left, yellow = start preparing compaction, red = hand off now
  if [ "$ctx_used" -ge 75 ] 2>/dev/null; then
    ctx_color="$RED"
  elif [ "$ctx_used" -ge 60 ] 2>/dev/null; then
    ctx_color="$YELLOW"
  else
    ctx_color="$GREEN"
  fi
  l2+="${ctx_color}${ctx_str}${RESET}"
fi
[ -n "$l2" ] && printf '%s' "$l2"
