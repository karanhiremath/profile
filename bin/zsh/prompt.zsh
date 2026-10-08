# Render immediately. Git runs in a pipe worker and updates the prompt via ZLE.
# Never splice repo-controlled branch text into PROMPT's shell program.
setopt PROMPT_SUBST
# Preserve the outstanding descriptor across `source ~/.zshrc` reloads.
typeset -g _profile_git_segment="${_profile_git_segment:-}"
typeset -g _profile_git_pwd="${_profile_git_pwd:-}"
typeset -g _profile_git_fd="${_profile_git_fd:-}"

_profile_git_worker() {
    local cwd="$1" output branch='' dirty=0
    local -a lines
    if output="$(command git -C "$cwd" status --porcelain=v1 --branch 2>/dev/null)"; then
        lines=("${(@f)output}")
        branch="${lines[1]#\#\# }"
        branch="${branch%%...*}"
        branch="${branch#No commits yet on }"
        branch="${branch#Initial commit on }"
        (( ${#lines} > 1 )) && dirty=1
    fi
    print -r -- "$cwd"$'\n'"$branch"$'\n'"$dirty"
}

_profile_prompt_render() {
    # Variable expansion is not recursively evaluated. Escape branch '%' before
    # it reaches prompt-percent expansion so repo names cannot inject controls.
    PROMPT='%F{9}%D{%Y-%m-%d %H:%M:%S}%f %F{11}|%f %F{12}%n%f%F{9}@%m%f %F{11}|%f %F{9}%~%f '
    PROMPT+="${prompt_newline:-}"
    PROMPT+='${_profile_git_segment}%F{11}>%f %F{15}'
}

_profile_git_ready() {
    local fd="$1" cwd branch dirty color=10
    if [[ -z "${2:-}" || "${2:-}" == hup ]] &&
            IFS= read -r -u "$fd" cwd &&
            IFS= read -r -u "$fd" branch &&
            IFS= read -r -u "$fd" dirty; then
        if [[ "$cwd" == "$PWD" ]]; then
            _profile_git_segment=''
            if [[ -n "$branch" ]]; then
                [[ "$dirty" == 1 ]] && color=9
                _profile_git_segment="%F{9}(%f%F{$color}${branch//\%/%%}%f%F{9})%f "
            fi
        fi
    fi
    zle -F "$fd" 2>/dev/null
    exec {fd}<&-
    _profile_git_fd=''
    _profile_prompt_render
    zle reset-prompt 2>/dev/null || true
}

precmd() {
    if [[ "$_profile_git_pwd" != "$PWD" ]]; then
        _profile_git_segment=''
        _profile_git_pwd="$PWD"
    fi
    _profile_prompt_render
    # At most one worker per shell; never cancel an in-flight git operation.
    # Newline-containing directories cannot use this line-oriented protocol.
    if [[ -z "$_profile_git_fd" && "$PWD" != *$'\n'* ]] && (( $+commands[git] )); then
        exec {_profile_git_fd}< <(exec 2>/dev/null 3>&-; _profile_git_worker "$PWD")
        zle -F "$_profile_git_fd" _profile_git_ready
    fi
    return 0
}
_profile_prompt_render
