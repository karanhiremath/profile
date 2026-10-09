# Sourced once at the end of zshrc.bootstrap, after host-local PATH mutations.
# Tool shims select repo-pinned versions without starting mise at shell startup.
# Full environment hooks are opt-in, or initialized on the first explicit mise
# command. A background process cannot update this shell's environment.
_profile_mise_shims="${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}/shims"
if (( $+commands[mise] )) || [[ -x /opt/homebrew/bin/mise ]]; then
    _profile_mise_binary="${commands[mise]:-/opt/homebrew/bin/mise}"
    if [[ "${PROFILE_MISE_MODE:-shims}" == activate ]]; then
        eval "$(command "$_profile_mise_binary" activate zsh)"
    else
        typeset -U path
        path=("$_profile_mise_shims" $path)
        mise() {
            local activation
            unset -f mise
            activation="$(command "$_profile_mise_binary" activate zsh)" || return
            eval "$activation"
            mise "$@"
        }
    fi
fi
unset _profile_mise_shims

# Environment exports were resolved with shell builtins. Shim repair is I/O
# maintenance and belongs outside the foreground startup path.
if (( $+functions[herm_fork_ensure_shim] )); then
    (herm_fork_ensure_shim) </dev/null >/dev/null 2>&1 &!
fi

_profile_omp_cache="${XDG_CACHE_HOME:-$HOME/.cache}/profile/zsh/omp.zsh"
if [[ -r "$_profile_omp_cache" ]]; then
    source "$_profile_omp_cache"
elif (( $+commands[omp] )); then
    # Cold starts remain usable. Pick up the completed cache in this shell on
    # a subsequent prompt, not just in future shells (children cannot compdef here).
    _profile_omp_load_cache() {
        if [[ -r "$_profile_omp_cache" ]]; then
            source "$_profile_omp_cache"
            add-zsh-hook -d precmd _profile_omp_load_cache
            unset -f _profile_omp_load_cache
        fi
    }
    autoload -Uz add-zsh-hook
    add-zsh-hook precmd _profile_omp_load_cache
fi

if (( $+commands[omp] )); then
    zmodload zsh/datetime
    zmodload zsh/stat
    typeset -A _profile_cache_stat
    _profile_cache_refresh=0
    if ! zstat -H _profile_cache_stat "$_profile_omp_cache" 2>/dev/null; then
        _profile_cache_refresh=1
    elif (( EPOCHSECONDS - _profile_cache_stat[mtime] > 86400 )); then
        _profile_cache_refresh=1
    elif [[ "${commands[omp]}" -nt "$_profile_omp_cache" ||
            "$_profile_dir/bin/zsh/refresh-completions" -nt "$_profile_omp_cache" ]]; then
        _profile_cache_refresh=1
    fi
    if (( _profile_cache_refresh )); then
        # Disowned, no terminal I/O, no waiting at shell exit. The worker uses
        # a kernel lock and atomic replacement; many new tabs still spawn one CLI.
        command zsh -df "$_profile_dir/bin/zsh/refresh-completions" \
            "${_profile_omp_cache:h}" "${commands[omp]}" \
            </dev/null >/dev/null 2>&1 &!
    fi
    unset _profile_cache_stat _profile_cache_refresh
fi
