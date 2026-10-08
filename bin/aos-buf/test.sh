#!/usr/bin/env bash
# aos-buf catalog/set/apply smoke. Headless nvim only. No Cos panes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cd "$ROOT/bin/aos-buf"
cargo test --quiet
cargo build --quiet
BUF="$ROOT/bin/aos-buf/target/debug/aos-buf"
export AOS_BUF="$BUF"
export ATOP_VI_HELPER="$ROOT/bin/atop/vi-request.lua"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/aos-buf-test.XXXXXX")"
cleanup() {
  if [[ -n "${NVIM_PID:-}" ]]; then
    kill "$NVIM_PID" 2>/dev/null || true
    wait "$NVIM_PID" 2>/dev/null || true
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

export TMPDIR="$WORKDIR"
export ATOP_VI_JOBDIR="$WORKDIR/jobs"
SOCKDIR="$WORKDIR/nvim.${USER}/t"
mkdir -p "$SOCKDIR" "$ATOP_VI_JOBDIR"
chmod 700 "$WORKDIR/nvim.${USER}" "$SOCKDIR" "$ATOP_VI_JOBDIR"

PROMPT="$WORKDIR/atop-vi-bg-smoke.md"
SRC="$WORKDIR/packet.md"
SRC2="$WORKDIR/packet2.md"
printf 'original-line\n' >"$PROMPT"
printf 'queued-write\n' >"$SRC"
printf 'wait-write\n' >"$SRC2"

SOCK="$SOCKDIR/nvim.$$.0"
nvim --headless -u NONE -n --listen "$SOCK" "$PROMPT" >/dev/null 2>&1 &
NVIM_PID=$!
for _ in $(seq 1 50); do
  [[ -S "$SOCK" ]] && break
  sleep 0.05
done
[[ -S "$SOCK" ]] || fail "headless nvim socket missing"

"$BUF" catalog | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["schema"]=="atop-vi.catalog.v1"; assert any(e.get("id")=="atop-vi-bg-smoke" for e in d["entries"]), d'

t0="$(python3 -c 'import time; print(time.time())')"
set_out="$("$BUF" set atop-vi-bg-smoke --file "$SRC")"
t1="$(python3 -c 'import time; print(time.time())')"
export T0="$t0" T1="$t1"
printf '%s' "$set_out" | python3 -c '
import json, sys, os
rec = json.load(sys.stdin)
assert rec.get("schema") == "atop-vi.job.v1", rec
assert rec.get("status") == "running", rec
assert rec.get("apply", {}).get("schema") == "aos.apply.v1", rec
assert (float(os.environ["T1"]) - float(os.environ["T0"])) < 8
' || fail "set receipt: $set_out"
JOB_ID="$(printf '%s' "$set_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

ok=0
for _ in $(seq 1 40); do
  job_out="$("$BUF" job "$JOB_ID")"
  if printf '%s' "$job_out" | python3 -c 'import json,sys; rec=json.load(sys.stdin); raise SystemExit(0 if rec.get("status")=="ok" else 1)'; then
    ok=1
    break
  fi
  sleep 0.1
done
[[ "$ok" == 1 ]] || fail "job did not complete: $("$BUF" job "$JOB_ID")"
rg -qx 'queued-write' "$PROMPT" || fail "background set did not write"

wait_out="$("$BUF" set atop-vi-bg-smoke --wait --file "$SRC2")"
printf '%s' "$wait_out" | rg -q '^wrote ' || fail "wait set: $wait_out"
rg -qx 'wait-write' "$PROMPT" || fail "--wait did not write"

apply_out="$("$ROOT/bin/aos" apply atop-vi-bg-smoke --file "$SRC")"
printf '%s' "$apply_out" | python3 -c 'import json,sys; rec=json.load(sys.stdin); assert rec["schema"]=="aos.apply.v1", rec' || fail "aos apply receipt: $apply_out"

echo OK
