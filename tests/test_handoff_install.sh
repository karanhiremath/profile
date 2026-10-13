#!/usr/bin/env bash
# Offline install-scope regression. No credentials, models, or live sessions.
set -euo pipefail
case "${1:-}" in -h|--help) printf 'Usage: tests/test_handoff_install.sh\n'; exit 0 ;; esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
mkdir -p "$TEMP/agent/extensions"
printf 'fixture-settings\n' > "$TEMP/agent/settings.json"
printf 'fixture-auth-not-a-secret\n' > "$TEMP/agent/auth.json"
printf 'fixture-unrelated-extension\n' > "$TEMP/agent/extensions/unrelated.ts"
cp "$TEMP/agent/settings.json" "$TEMP/settings.before"
cp "$TEMP/agent/auth.json" "$TEMP/auth.before"
cp "$TEMP/agent/extensions/unrelated.ts" "$TEMP/unrelated.before"
PI_CODING_AGENT_DIR="$TEMP/agent" "$ROOT/bin/atop/harness-sync" apply-handoff > "$TEMP/result.json"
grep -Fx '{"state":"installed","stack":"pi-handoff","reload_required":true}' "$TEMP/result.json"
cmp "$TEMP/settings.before" "$TEMP/agent/settings.json"
cmp "$TEMP/auth.before" "$TEMP/agent/auth.json"
cmp "$TEMP/unrelated.before" "$TEMP/agent/extensions/unrelated.ts"
cmp "$ROOT/config/pi/extensions/handoff.ts" "$TEMP/agent/extensions/handoff.ts"
cmp "$ROOT/config/pi/extensions/compact-handoff.ts" "$TEMP/agent/extensions/compact-handoff.ts"
cmp "$ROOT/config/pi/extensions/lib/compact-snapshot.ts" "$TEMP/agent/extensions/lib/compact-snapshot.ts"
# A second install is safe and does not leave staging files.
PI_CODING_AGENT_DIR="$TEMP/agent" "$ROOT/bin/atop/harness-sync" apply-handoff > "$TEMP/repeat.json"
cmp "$TEMP/result.json" "$TEMP/repeat.json"
test "$(find "$TEMP/agent/extensions" -name '*.XXXXXX' | wc -l | tr -d ' ')" = 0
