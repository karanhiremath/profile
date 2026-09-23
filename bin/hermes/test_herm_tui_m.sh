#!/usr/bin/env bash
# Dry-run checks for herm-tui-m alias mapping. No session attach.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
M="$DIR/herm-tui-m"
fail() { echo "FAIL: $*" >&2; exit 1; }

out="$("$M" notes --dry-run)"
printf '%s\n' "$out" | grep -q '^profile=personal-notes-steward$' || fail "notes profile: $out"
printf '%s\n' "$out" | grep -q '^session=notes$' || fail "notes session: $out"
printf '%s\n' "$out" | grep -q '^target=notes:m$' || fail "notes target: $out"
printf '%s\n' "$out" | grep -q '^surface=cli$' || fail "notes surface: $out"
printf '%s\n' "$out" | grep -q -- '--continue --cli' || fail "notes launch: $out"

out="$("$M" cos --dry-run)"
printf '%s\n' "$out" | grep -q '^profile=chief-of-staff$' || fail "cos profile: $out"
printf '%s\n' "$out" | grep -q '^session=cos$' || fail "cos session: $out"
if "$DIR/alias_seat.py" lock-pid chief-of-staff >/dev/null 2>&1; then
  printf '%s\n' "$out" | grep -Eq '^action=attach-live-tui$' || fail "cos live lock action: $out"
  printf '%s\n' "$out" | grep -Eq '^lock_held=1$' || fail "cos live lock_held: $out"
else
  printf '%s\n' "$out" | grep -Eq '^lock_held=0$' || fail "cos dry-run should report lock_held=0: $out"
fi

if "$M" notesw --dry-run >/tmp/herm-tui-m-notesw.out 2>/tmp/herm-tui-m-notesw.err; then
  grep -q '^profile=' /tmp/herm-tui-m-notesw.out || fail "notesw succeeded without profile"
else
  grep -q 'work notes steward profile not found' /tmp/herm-tui-m-notesw.err \
    || fail "notesw missing work-lane error: $(cat /tmp/herm-tui-m-notesw.err)"
fi

if "$M" cosw --dry-run >/tmp/herm-tui-m-cosw.out 2>/tmp/herm-tui-m-cosw.err; then
  grep -q '^profile=chief-of-staff-work$' /tmp/herm-tui-m-cosw.out || fail "cosw profile"
else
  grep -q 'chief-of-staff-work profile not found' /tmp/herm-tui-m-cosw.err \
    || fail "cosw missing work-lane error: $(cat /tmp/herm-tui-m-cosw.err)"
fi

echo "herm-tui-m dry-run checks passed"
