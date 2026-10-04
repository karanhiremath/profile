# zsh plugin stack. Guarded so ~/.zshrc + zsh_profile double-source is a no-op.
[[ -n ${_PROFILE_ZSH_PLUGINS_LOADED:-} ]] && return
_PROFILE_ZSH_PLUGINS_LOADED=1

_profile_zsh_plugin_home="${XDG_DATA_HOME:-$HOME/.local/share}/zsh/plugins"
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

# Autosuggestions before fzf-tab / highlighting.
_profile_source_first \
  "${_profile_brew_prefix}/share/zsh-autosuggestions/zsh-autosuggestions.zsh" \
  "${_profile_zsh_plugin_home}/zsh-autosuggestions/zsh-autosuggestions.zsh"

# Extra completion dirs are added in zsh_profile.sh before the one
# guarded `compinit -u`. Do not append them here — late fpath changes
# are invisible unless compinit runs again.

# fzf-tab after compinit, before syntax highlighting.
_profile_source_first \
  "${_profile_zsh_plugin_home}/fzf-tab/fzf-tab.plugin.zsh" \
  "${_profile_brew_prefix}/share/fzf-tab/fzf-tab.plugin.zsh"

# Syntax highlighting must be last among plugins.
if [[ -d "${_profile_brew_prefix}/share/zsh-syntax-highlighting/highlighters" ]]; then
  export ZSH_HIGHLIGHT_HIGHLIGHTERS_DIR="${_profile_brew_prefix}/share/zsh-syntax-highlighting/highlighters"
fi
_profile_source_first \
  "${_profile_brew_prefix}/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" \
  "${_profile_zsh_plugin_home}/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"

unset _profile_zsh_plugin_home _profile_brew_prefix
unfunction _profile_source_first
