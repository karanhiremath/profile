#!/usr/bin/env bash
set -euo pipefail

printf 'host=%s\n' "$(scutil --get LocalHostName 2>/dev/null || hostname)"
printf 'utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -d /Applications/Dia.app ]]; then
  printf 'dia=present\n'
else
  printf 'dia=absent\n'
fi

if [[ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
  printf 'chrome=present\n'
else
  printf 'chrome=absent\n'
fi

if command -v browser-use >/dev/null 2>&1; then
  printf 'browser_use_cli=present\n'
else
  printf 'browser_use_cli=absent\n'
fi

if python3 -c 'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("browser_use") else 1)' 2>/dev/null; then
  printf 'browser_use_py=present\n'
else
  printf 'browser_use_py=absent\n'
fi

settings="${HOME}/.pi/agent/settings.json"
if [[ -f "$settings" ]] && rg -q 'pi-browser-harness' "$settings"; then
  printf 'pi_browser_harness=settings\n'
else
  printf 'pi_browser_harness=absent\n'
fi

if [[ -f "${HOME}/.pi/agent/browser-harness.json" ]]; then
  printf 'browser_harness_state=present\n'
else
  printf 'browser_harness_state=absent\n'
fi

idx="${HOME}/.pi/agent/buffers/INDEX.jsonl"
if [[ -f "$idx" ]]; then
  printf 'buffer_index_mtime=%s\n' "$(stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%SZ' "$idx")"
else
  printf 'buffer_index=absent\n'
fi

sync="${HOME}/.pi/agent/buffers/sync.log"
if [[ -f "$sync" ]]; then
  printf 'buffer_sync_tail=%s\n' "$(tail -n 1 "$sync")"
fi
