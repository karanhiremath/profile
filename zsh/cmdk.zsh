# cmdk widget + piclass. Sourced from zsh_profile.sh.
[[ -n ${_PROFILE_ZSH_CMDK_LOADED:-} ]] && return
_PROFILE_ZSH_CMDK_LOADED=1

CMDK_BIN="${PROFILE_DIR:-$HOME/src/profile}/bin/cmdk/cmdk"

function cmdk() {
  "$CMDK_BIN" "$@"
}

function piclass() {
  local cls="${1:?usage: piclass <class> [agent]}"
  export PI_PROFILE_CLASS="$cls"
  if [[ -n "${2:-}" ]]; then
    export PI_PROFILE_AGENT="$2"
  fi
  print -r -- "PI_PROFILE_CLASS=${PI_PROFILE_CLASS}${PI_PROFILE_AGENT:+ PI_PROFILE_AGENT=${PI_PROFILE_AGENT}}"
}

_cmdk_widget() {
  cmdk pick
  zle reset-prompt
}
zle -N _cmdk_widget
bindkey '^Xk' _cmdk_widget
bindkey '^X^K' _cmdk_widget
