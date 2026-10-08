#!/usr/bin/env bash
# atop vi set/job smoke. Uses a throwaway headless nvim. Does not touch Cos panes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VI="$ROOT/bin/atop/vi"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

if [[ -x "$ROOT/bin/aos-buf/target/debug/aos-buf" || -x "$ROOT/bin/aos-buf/target/release/aos-buf" ]]; then
  :
elif [[ -f "$ROOT/bin/aos-buf/Cargo.toml" ]]; then
  cargo build --quiet --manifest-path "$ROOT/bin/aos-buf/Cargo.toml" || fail "aos-buf build"
fi
if [[ -x "$ROOT/bin/aos-buf/target/debug/aos-buf" ]]; then
  export AOS_BUF="$ROOT/bin/aos-buf/target/debug/aos-buf"
elif [[ -x "$ROOT/bin/aos-buf/target/release/aos-buf" ]]; then
  export AOS_BUF="$ROOT/bin/aos-buf/target/release/aos-buf"
fi
export ATOP_VI_HELPER="$ROOT/bin/atop/vi-request.lua"

"$VI" --help | rg -q 'queue write' || fail "help mentions queued set"
"$VI" jobs >/dev/null || fail "jobs"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/atop-vi-test.XXXXXX")"
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

# Default set must return a running/queued job without --wait.
t0="$(python3 -c 'import time; print(time.time())')"
set_out="$("$VI" atop-vi-bg-smoke set --file "$SRC")"
t1="$(python3 -c 'import time; print(time.time())')"
export T0="$t0" T1="$t1"
printf '%s' "$set_out" | python3 -c '
import json, sys, os
rec = json.load(sys.stdin)
assert rec.get("schema") == "atop-vi.job.v1", rec
assert rec.get("status") == "running", rec
assert rec.get("id") and rec.get("pid"), rec
assert (float(os.environ["T1"]) - float(os.environ["T0"])) < 8
' || fail "set receipt: $set_out"
JOB_ID="$(printf '%s' "$set_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

ok=0
for _ in $(seq 1 40); do
  job_out="$("$VI" job "$JOB_ID")"
  if printf '%s' "$job_out" | python3 -c 'import json,sys; rec=json.load(sys.stdin); raise SystemExit(0 if rec.get("status")=="ok" else 1)'; then
    ok=1
    break
  fi
  sleep 0.1
done
[[ "$ok" == 1 ]] || fail "job did not complete: $("$VI" job "$JOB_ID")"
rg -qx 'queued-write' "$PROMPT" || fail "background set did not write file"

wait_out="$("$VI" atop-vi-bg-smoke set --wait --file "$SRC2")"
printf '%s' "$wait_out" | rg -q '^wrote ' || fail "wait set: $wait_out"
rg -qx 'wait-write' "$PROMPT" || fail "--wait set did not write file"

"$VI" jobs | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["schema"]=="atop-vi.jobs.v1"; assert any(j.get("id")==sys.argv[1] for j in d.get("jobs") or []), d' "$JOB_ID" || fail "jobs missing id"

echo OK
