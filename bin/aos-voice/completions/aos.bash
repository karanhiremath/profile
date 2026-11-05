# Optional: source this file in Bash. No filesystem/network target discovery.
_aos_voice_complete() {
    local offset=1 current="${COMP_WORDS[COMP_CWORD]}" choice choices
    COMPREPLY=()
    if [[ "${COMP_WORDS[0]##*/}" == aos ]]; then
        if [[ "$COMP_CWORD" -eq 1 ]]; then
            while IFS= read -r choice; do COMPREPLY+=("$choice"); done < <(compgen -W 'status sync pull doctor buf policy voice atop hosts bus install help' -- "$current")
            return
        fi
        [[ "${COMP_WORDS[1]}" == voice ]] || return
        offset=2
    fi
    if [[ "$COMP_CWORD" -eq "$offset" ]]; then
        choices='status doctor targets bind connect join disconnect leave dispatch renderer'
    else
        choices='--fake --dry-run --domain --target --generation --catalog --request --help'
    fi
    while IFS= read -r choice; do COMPREPLY+=("$choice"); done < <(compgen -W "$choices" -- "$current")
}
complete -F _aos_voice_complete aos aos-voice
