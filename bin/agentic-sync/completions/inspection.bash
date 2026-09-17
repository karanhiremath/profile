# Source explicitly; installation does not modify shell configuration.
_agentic_inspection_complete() {
  local words
  case "${COMP_WORDS[0]}" in
    repo-context)
      words='inspect routes --registry --repo --route --proposal-file --checkout --refresh --audience --format --help' ;;
    *)
      words='status plan run --dry-run --config --checkout --format --help' ;;
  esac
  COMPREPLY=()
  while IFS= read -r candidate; do
    COMPREPLY+=("$candidate")
  done < <(compgen -W "$words" -- "${COMP_WORDS[COMP_CWORD]}")
}
complete -F _agentic_inspection_complete repo-context agentic-sync-notes
