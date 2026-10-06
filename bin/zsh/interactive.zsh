# Sourced once at the end of zshrc.bootstrap, after host-local PATH mutations.
# Env integration must run in this shell; completion generation must not block it.
if (( $+commands[mise] )); then
    eval "$(command mise activate zsh)"
elif [[ -x /opt/homebrew/bin/mise ]]; then
    eval "$(/opt/homebrew/bin/mise activate zsh)"
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
