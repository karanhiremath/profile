#!/usr/bin/env bash
# Dry-run + cap + help. No network.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/pplx-research"
SYNC="$DIR/pplx-library-sync"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

"$BIN" --help | grep -q 'Opt-in Perplexity' || fail "help"
"$SYNC" --help | grep -q 'Library' || fail "sync help"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export PPLX_STATE_DIR="$tmp/state"

out="$("$BIN" --dry-run --mode search --purpose smoke --query 'hello perplexity')"
printf '%s\n' "$out" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d["schema_version"]=="perplexity-research.v1"
assert d["backend"]=="dry-run"
assert d["mode"]=="search"
assert d["audit"]["kind"]=="research.perplexity.query"
assert "PERPLEXITY" not in json.dumps(d).upper() or "perplexity-research" in d["schema_version"]
'

"$BIN" --dry-run --mode research --purpose x --query y >/dev/null 2>&1 && fail "research without confirm"
"$BIN" --dry-run --mode research --confirm-expensive --purpose x --query y >/dev/null

# live cap: fake usage then refuse a live call without hitting network
mkdir -p "$PPLX_STATE_DIR/usage"
printf '{"date":"ignore","units":20,"calls":[]}\n' > "$PPLX_STATE_DIR/usage/$(date -u +%Y-%m-%d).json"
export PERPLEXITY_API_KEY="test-not-used"
if "$BIN" --mode search --purpose cap --query 'blocked' >/dev/null 2>"$tmp/err"; then
  fail "cap should block"
fi
grep -q 'daily cap' "$tmp/err" || fail "cap message"

echo OK
