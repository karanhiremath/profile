#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../completions/aos.bash
source "$ROOT/completions/aos.bash"
COMP_WORDS=(aos voice jo)
COMP_CWORD=2
_aos_voice_complete
[[ "${COMPREPLY[*]}" == join ]]
COMP_WORDS=(aos-voice le)
COMP_CWORD=1
_aos_voice_complete
[[ "${COMPREPLY[*]}" == leave ]]
COMP_WORDS=(aos voi)
COMP_CWORD=1
_aos_voice_complete
[[ "${COMPREPLY[*]}" == voice ]]
