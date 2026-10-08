source ~/.config/.vars

alias reload="source ~/.zshrc && echo 'ZSH Profile Reloaded'"
alias relaod="reload"


autoload -U colors && colors
autoload -Uz promptinit && promptinit

# Register standard completion paths before the single audited compinit run.
# Keep the security audit: it costs tens of ms here, not the hundreds from CLIs.
typeset -U fpath
for _profile_completion_dir in /opt/homebrew/share/zsh/site-functions /usr/local/share/zsh/site-functions; do
    [[ -d "$_profile_completion_dir" ]] && fpath=("$_profile_completion_dir" $fpath)
done
unset _profile_completion_dir
autoload -Uz compinit
compinit

# fzf key bindings/completion for package-manager installs.
if command -v fzf >/dev/null 2>&1; then
    if [[ -r "${HOME}/.fzf.zsh" ]]; then
        source "${HOME}/.fzf.zsh"
    else
        fzf_zsh_dirs=()
        # Standard package locations need no Homebrew process at startup.
        [[ -n "${FZF_BASE:-}" ]] && fzf_zsh_dirs+=("${FZF_BASE}/shell")
        fzf_zsh_dirs+=(
            "${HOME}/.fzf/shell"
            "/usr/share/doc/fzf/examples"
            "/usr/share/fzf"
            "/opt/homebrew/opt/fzf/shell"
            "/usr/local/opt/fzf/shell"
        )
        for fzf_zsh_dir in "${fzf_zsh_dirs[@]}"; do
            [[ -r "${fzf_zsh_dir}/completion.zsh" ]] && source "${fzf_zsh_dir}/completion.zsh" && break
        done
        for fzf_zsh_dir in "${fzf_zsh_dirs[@]}"; do
            [[ -r "${fzf_zsh_dir}/key-bindings.zsh" ]] && source "${fzf_zsh_dir}/key-bindings.zsh" && break
        done
        unset fzf_zsh_dir fzf_zsh_dirs
    fi
fi

# No synchronous VCS probe on the first prompt or subsequent redraws.
source "${PROFILE_DIR}/bin/zsh/prompt.zsh"

bindkey "^[[H" beginning-of-line
bindkey "^[[F" end-of-line
bindkey  "^[[3~"  delete-char

if [[ "${TERM_PROGRAM:-}" == iTerm.app ]]; then
    source "${PROFILE_DIR}"/.iterm2_shell_integration.zsh
fi

# Add stuff to path
path=("$HOME/.local/bin" "$HOME/bin" $path)
path+=("$HOME/.cargo/bin")
export PATH

# mise activation and cached CLI completions are loaded once by the bootstrap,
# after host-local PATH changes. Completion generation runs in the background.

# pnpm global bin: `pnpm add -g` installs CLIs here AND requires this dir on PATH
# (otherwise pnpm errors "The configured global bin directory is not in PATH").
export PNPM_HOME="${HOME}/.local/share/pnpm"
path=("$PNPM_HOME/bin" $path)
export PATH

# doesnt seem to have an arm64 build for mac
# eval "$(starship init zsh)"
