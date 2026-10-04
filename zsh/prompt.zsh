# Prompt + right chip. Layer/session from cmdk; git from vcs_info (zsh_profile).
[[ -n ${_PROFILE_ZSH_PROMPT_LOADED:-} ]] && return
_PROFILE_ZSH_PROMPT_LOADED=1

autoload -Uz vcs_info
zstyle ':vcs_info:git:*' formats '%b'
setopt PROMPT_SUBST

_profile_cmdk_chip() {
  if [[ -n "${TMUX:-}" ]]; then
    command tmux display-message -p '#S:#W #{pane_current_command}' 2>/dev/null
  else
    print -n -- "local zsh"
  fi
}

_profile_precmd_prompt() {
  vcs_info
  local chip git_color=10
  chip="$(_profile_cmdk_chip)"
  if [[ -n ${vcs_info_msg_0_} ]]; then
    if command git status --porcelain 2>/dev/null | command tail -n1 | grep -q .; then
      git_color=9
    fi
    PROMPT="%F{9}%D{%Y-%m-%d %H:%M:%S}%f %F{11}|%f %F{12}%n%f%F{9}@%m%f %F{11}|%f %F{9}%~%f $prompt_newline%F{9}(%f%F{${git_color}}${vcs_info_msg_0_}%f%F{9})%f %F{11}>%f %F{15}"
  else
    PROMPT="%F{9}%D{%Y-%m-%d %H:%M:%S}%f %F{11}|%f %F{12}%n%f%F{9}@%m%f %F{11}|%f %F{9}%~%f $prompt_newline %F{11}>%f %F{15}"
  fi
  RPROMPT="%F{11}${chip}%f"
}

precmd_functions=(_profile_precmd_prompt $precmd_functions)
