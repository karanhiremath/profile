#!/usr/bin/env bash
# aos update unit + dry-run smoke. No GitHub mutation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cd "$ROOT/bin/aos-buf"
cargo test --quiet update::
cargo build --quiet --bin aos
AOS="$ROOT/bin/aos-buf/target/debug/aos"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/aos-update-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
export PROFILE_DIR="$ROOT"
export AOS_PIN_FILE="$TMP/pin.env"
export HOME="$TMP/home"
mkdir -p "$HOME"

printf 'AOS_REPO=karanhiremath/profile\nAOS_PIN_TAG=\n' >"$AOS_PIN_FILE"
out="$("$AOS" update --dry-run --from-source --dest "$TMP/bin/aos")"
printf '%s' "$out" | python3 -c '
import json, sys
rec = json.load(sys.stdin)
assert rec.get("schema") == "aos.update.v1", rec
assert rec.get("mode") == "source", rec
'
ver="$("$AOS" version)"
[[ -n "$ver" ]] || fail "empty version"

# wrapper dispatches update
wrap_out="$("$ROOT/bin/aos" update --dry-run --from-source --dest "$TMP/bin/aos2")"
printf '%s' "$wrap_out" | python3 -c '
import json, sys
rec = json.load(sys.stdin)
assert rec.get("schema") == "aos.update.v1", rec
'

echo OK
