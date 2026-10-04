# fzf keybindings + profile aliases. Does nothing when fzf is missing.
[[ -n ${_PROFILE_ZSH_FZF_LOADED:-} ]] && return
_PROFILE_ZSH_FZF_LOADED=1

if ! command -v fzf >/dev/null 2>&1; then
  return
fi

_profile_brew_prefix=""
if command -v brew >/dev/null 2>&1; then
  _profile_brew_prefix="$(brew --prefix 2>/dev/null)"
fi

_profile_source_first() {
  local f
  for f in "$@"; do
    if [[ -r "$f" ]]; then
      source "$f"
      return 0
    fi
  done
  return 1
}

_profile_source_first \
  "${_profile_brew_prefix}/opt/fzf/shell/key-bindings.zsh" \
  "${_profile_brew_prefix}/share/fzf/shell/key-bindings.zsh" \
  /usr/share/doc/fzf/examples/key-bindings.zsh

_profile_source_first \
  "${_profile_brew_prefix}/opt/fzf/shell/completion.zsh" \
  "${_profile_brew_prefix}/share/fzf/shell/completion.zsh" \
  /usr/share/doc/fzf/examples/completion.zsh

export FZF_DEFAULT_OPTS="${FZF_DEFAULT_OPTS:-} --height=60% --reverse --border"

# Alias-oriented fzf helpers (keep fvi from myprofile.sh).
function fattach() {
  local sess
  sess=$(command tmux list-sessions -F '#S' 2>/dev/null | fzf --prompt='attach> ') || return
  attach "$sess"
}

function fpc() {
  if command -v pc >/dev/null 2>&1; then
    local project
    project=$(pc list 2>/dev/null | awk '{print $2}' | fzf --prompt='pc> ') || return
    pc "$project"
  else
    pc
  fi
}

function ffleet() {
  local lane
  lane=$(printf '%s\n' ao0 ao1 ao2 ao3 ao4 infra0 infra1 infra2 infra3 infra4 \
    | fzf --prompt='fleet> ') || return
  fw "$lane"
}

function fclass() {
  local cls
  cls=$(cmdk classes 2>/dev/null | python3 -c '
import json,sys
data=json.load(sys.stdin)
for item in data.get("classes") or []:
    if not item.startswith("agent:"):
        print(item)
') || return
  cls=$(print -r -- "$cls" | fzf --prompt='piclass> ') || return
  piclass "$cls"
}

unset _profile_brew_prefix
unfunction _profile_source_first
