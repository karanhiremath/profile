#!/usr/bin/env bash
# Dry-run --lane plans. Does not attach live Cos / CosW / herm-tui.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $*" >&2; exit 1; }

cos_plan="$("$DIR/cos" --print-plan)"
o1="$("$DIR/cos" --lane o1 --print-plan)"
o2="$("$DIR/cos" --lane=o2 --print-plan)"
printf '%s\n' "$cos_plan" | grep -q '"profile": "chief-of-staff"' || fail "default cos profile: $cos_plan"
printf '%s\n' "$cos_plan" | grep -q '"session": "cos"' || fail "default cos session: $cos_plan"
printf '%s\n' "$o1" | grep -q '"profile": "chief-of-staff-o1"' || fail "cos --lane o1 profile: $o1"
printf '%s\n' "$o1" | grep -q '"session": "cos-o1"' || fail "cos --lane o1 session: $o1"
printf '%s\n' "$o2" | grep -q '"session": "cos-o2"' || fail "cos --lane o2 session: $o2"
printf '%s\n' "$o1" | grep -q 'hermes-agents/chief-of-staff-o1' || fail "cos --lane o1 home: $o1"
if [ "$o1" = "$o2" ]; then
  fail "o1 and o2 plans must differ"
fi
if [ "$o1" = "$cos_plan" ]; then
  fail "lane plan must not reuse the default cos seat"
fi

if "$DIR/cos" --lane work --print-plan >/tmp/cos-lane-work.out 2>/tmp/cos-lane-work.err; then
  fail "cos --lane work must collide with chief-of-staff-work"
fi
grep -q 'collides' /tmp/cos-lane-work.err || fail "collision error: $(cat /tmp/cos-lane-work.err)"

work="$("$DIR/cosw" --lane o1 --print-plan)"
printf '%s\n' "$work" | grep -q '"profile": "chief-of-staff-work-o1"' || fail "cosw --lane o1 profile: $work"
printf '%s\n' "$work" | grep -q '"session": "cosw-o1"' || fail "cosw --lane o1 session: $work"
printf '%s\n' "$work" | grep -q 'hermes-agents/chief-of-staff-work-o1' || fail "cosw --lane o1 home: $work"

echo "lane-isolation dry-run checks passed"
