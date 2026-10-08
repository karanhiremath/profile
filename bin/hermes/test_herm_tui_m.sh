#!/usr/bin/env bash
# Dry-run checks for herm-tui-m alias mapping + spawn-always contract.
# Hermetic: isolated data home + fake tmux. No session attach.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
M="$DIR/herm-tui-m"
fail() { echo "FAIL: $*" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/data"
# Fake tmux: every probe reports empty/free (deterministic minting).
printf '#!/usr/bin/env bash\nexit 1\n' > "$tmp/bin/tmux"
chmod +x "$tmp/bin/tmux"
export PATH="$tmp/bin:$PATH"
export HERMES_AGENTS_DATA_HOME="$tmp/data"

out="$("$M" notes --dry-run)"
printf '%s\n' "$out" | grep -q '^profile=personal-notes-steward$' || fail "notes profile: $out"
printf '%s\n' "$out" | grep -q '^session=notes$' || fail "notes session: $out"
printf '%s\n' "$out" | grep -q '^target=notes:m$' || fail "notes target: $out"
printf '%s\n' "$out" | grep -q '^surface=cli$' || fail "notes surface: $out"
printf '%s\n' "$out" | grep -q -- '--continue --cli' || fail "notes launch: $out"

out="$("$M" cos --dry-run)"
printf '%s\n' "$out" | grep -q '^profile=chief-of-staff$' || fail "cos profile: $out"
printf '%s\n' "$out" | grep -q '^session=cos$' || fail "cos session: $out"
printf '%s\n' "$out" | grep -q '^lock_held=0$' || fail "cos dry-run should report lock_held=0: $out"
printf '%s\n' "$out" | grep -q '^action=launch$' || fail "cos free action must be launch: $out"

if "$M" notesw --dry-run >/tmp/herm-tui-m-notesw.out 2>/tmp/herm-tui-m-notesw.err; then
  grep -q '^profile=' /tmp/herm-tui-m-notesw.out || fail "notesw succeeded without profile"
else
  grep -q 'work notes steward profile not found' /tmp/herm-tui-m-notesw.err \
    || fail "notesw missing work-lane error: $(cat /tmp/herm-tui-m-notesw.err)"
fi

# cosw free seat: launch on the canonical session.
out="$("$M" cosw --dry-run)"
printf '%s\n' "$out" | grep -q '^profile=chief-of-staff-work$' || fail "cosw free profile: $out"
printf '%s\n' "$out" | grep -q '^session=cosw$' || fail "cosw free session: $out"
printf '%s\n' "$out" | grep -q '^action=launch$' || fail "cosw free action: $out"

# cosw busy seat: spawn-always mints sibling cosw-a1; never attach.
mkdir -p "$tmp/data/chief-of-staff-work"
printf '%s\n' "$$" > "$tmp/data/chief-of-staff-work/.herm-tui.lock"
out="$("$M" cosw --dry-run)"
printf '%s\n' "$out" | grep -q '^lock_held=1$' || fail "cosw busy lock_held: $out"
printf '%s\n' "$out" | grep -q '^profile=chief-of-staff-work-a1$' || fail "cosw busy must mint sibling profile: $out"
printf '%s\n' "$out" | grep -q '^session=cosw-a1$' || fail "cosw busy must mint cosw-a1: $out"
printf '%s\n' "$out" | grep -q '^action=launch$' || fail "cosw busy action must stay launch: $out"

# Explicit attach subcommand stays available.
out="$("$M" cosw attach --dry-run)"
printf '%s\n' "$out" | grep -q '^subcmd=attach$' || fail "cosw attach subcmd: $out"
printf '%s\n' "$out" | grep -q '^action=attach$' || fail "cosw attach action: $out"

# sessions subcommand lists the family (fake tmux -> empty list, shape held).
"$M" cosw sessions | grep -q '"base_session": "cosw"' || fail "cosw sessions listing"

echo "herm-tui-m dry-run checks passed"