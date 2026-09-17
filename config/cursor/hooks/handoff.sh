#!/usr/bin/env bash
# Cursor preCompact/stop → pi pointer-handoff hook. Fail open.
set -euo pipefail
HOOK="${PI_HANDOFF_CURSOR_HOOK:-$HOME/.pi/agent/extensions/lib/handoff-cursor-hook.ts}"
if [ ! -f "$HOOK" ]; then
  printf '%s\n' '{}'
  exit 0
fi
BUN="${BUN:-$HOME/.local/share/hermes-toolchain/bun/bin/bun}"
if [ -x "$BUN" ]; then
  exec "$BUN" "$HOOK"
fi
if command -v bun >/dev/null 2>&1; then
  exec bun "$HOOK"
fi
if command -v npx >/dev/null 2>&1; then
  exec npx --yes tsx "$HOOK"
fi
printf '%s\n' '{}'
exit 0
