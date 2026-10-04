#!/usr/bin/env bash
# Spawn-always contract: launchers NEVER attach to an existing TUI; busy seats
# mint sibling seats (a1, a2, ...) with their own home + tmux session. Attaching
# is explicit only (agents attach / cosw attach); listing is agents sessions.
# Dry-run only: fake tmux shim, isolated data home; never attaches live TUIs.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $*" >&2; exit 1; }

PY="${HERMES_PYTHON_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/hermes-toolchain}/venv/bin/python"
[ -x "$PY" ] || PY=python3
SEAT="$DIR/alias_seat.py"
[ -f "$SEAT" ] || fail "missing $SEAT"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/data"

# Fake tmux: every has-session probe reports "free" so next-seat is deterministic.
cat > "$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$tmp/bin/tmux"
export PATH="$tmp/bin:$PATH"
export HERMES_AGENTS_DATA_HOME="$tmp/data"

plan="$("$PY" "$SEAT" next-seat cosw)"
printf '%s\n' "$plan" | grep -q '"session": "cosw-a1"' || fail "next-seat cosw should mint cosw-a1: $plan"
printf '%s\n' "$plan" | grep -q '"profile": "chief-of-staff-work-a1"' || fail "next-seat profile: $plan"
printf '%s\n' "$plan" | grep -q 'chief-of-staff-work-a1' || fail "next-seat home root: $plan"
if printf '%s\n' "$plan" | grep -q '"session": "cosw-o1"'; then
  fail "next-seat must not collide with user lane namespace"
fi

# herm-tui-m spawn-always dry-runs (isolated data home; fake tmux = all free).
m_free="$("$DIR/herm-tui-m" cosw --dry-run)"
printf '%s\n' "$m_free" | grep -q '^action=launch$' || fail "m free action: $m_free"
printf '%s\n' "$m_free" | grep -q '^session=cosw$' || fail "m free session: $m_free"
printf '%s\n' "$m_free" | grep -q '^subcmd=none$' || fail "m free subcmd: $m_free"

m_attach="$("$DIR/herm-tui-m" cosw attach --dry-run)"
printf '%s\n' "$m_attach" | grep -q '^action=attach$' || fail "m attach action: $m_attach"
printf '%s\n' "$m_attach" | grep -q '^subcmd=attach$' || fail "m attach subcmd: $m_attach"

# Busy base home -> default launch mints sibling session cosw-a1 (never attach).
mkdir -p "$tmp/data/chief-of-staff-work"
printf '%s\n' "$$" > "$tmp/data/chief-of-staff-work/.herm-tui.lock"
m_busy="$("$DIR/herm-tui-m" cosw --dry-run)"
printf '%s\n' "$m_busy" | grep -q '^lock_held=1$' || fail "m busy lock_held: $m_busy"
printf '%s\n' "$m_busy" | grep -q '^session=cosw-a1$' || fail "m busy must mint cosw-a1: $m_busy"
printf '%s\n' "$m_busy" | grep -q '^profile=chief-of-staff-work-a1$' || fail "m busy profile: $m_busy"
printf '%s\n' "$m_busy" | grep -q '^action=launch$' || fail "m busy action: $m_busy"

m_sessions="$("$DIR/herm-tui-m" cosw sessions)"
printf '%s\n' "$m_sessions" | grep -q '"base_session": "cosw"' || fail "m sessions listing: $m_sessions"

# Held lock on the minted seat forces the next free sibling.
mkdir -p "$tmp/data/chief-of-staff-work-a1"
printf '%s\n' "$$" > "$tmp/data/chief-of-staff-work-a1/.herm-tui.lock"
held="$("$PY" "$SEAT" lock-pid chief-of-staff-work-a1)" || fail "lock-pid should detect held a1"
[ "$held" = "$$" ] || fail "lock-pid mismatch: $held"
plan2="$("$PY" "$SEAT" next-seat cosw)"
printf '%s\n' "$plan2" | grep -q '"session": "cosw-a2"' || fail "held a1 must skip to a2: $plan2"
printf '%s\n' "$plan2" | grep -q '"profile": "chief-of-staff-work-a2"' || fail "held a1 profile skip: $plan2"

# Family session listing shape (fake tmux -> zero sessions, keys still present).
listing="$("$PY" "$SEAT" sessions cosw)"
printf '%s\n' "$listing" | grep -q '"family": "cosw"' || fail "sessions family: $listing"
printf '%s\n' "$listing" | grep -q '"base_session": "cosw"' || fail "sessions base: $listing"

# cos family works the same way (no cross-family leakage).
cosplan="$("$PY" "$SEAT" next-seat cos)"
printf '%s\n' "$cosplan" | grep -q '"session": "cos-a1"' || fail "next-seat cos: $cosplan"
printf '%s\n' "$cosplan" | grep -q '"profile": "chief-of-staff-a1"' || fail "next-seat cos profile: $cosplan"

# Launcher contract (structural): the up path must not call attach_live_tui;
# the only remaining attach_live_tui call site is the explicit attach command.
grep -q 'attach_live_tui "$profile"' "$DIR/agents" \
  && fail "agents up still auto-attaches (attach_live_tui on \$profile)"
grep -q 'spawn-always' "$DIR/agents" || fail "agents up missing spawn-always gate"
grep -q 'mint_sibling_seat "$profile"' "$DIR/agents" || fail "agents up missing sibling mint"
grep -q 'agents" "$_cosw_sub"' "$DIR/cosw" || fail "cosw must route sessions/attach subcommands"
grep -qF '"${COS_ARGS[0]}"' "$DIR/cos" || fail "cos must route sessions/attach subcommands"
grep -q 'attach-live-tui' "$DIR/herm-tui-m" \
  && fail "herm-tui-m still has implicit attach-live-tui default"
grep -q 'mint_sibling "$ALIAS"' "$DIR/herm-tui-m" || fail "herm-tui-m missing sibling mint"

# Seat isolation still holds: explicit --lane seats keep their namespace and
# never collide with auto-minted a1.. seats.
[ "$("$PY" "$SEAT" lane-profile cosw o1)" = "chief-of-staff-work-o1" ] \
  || fail "lane-profile cosw o1 regression"
plan3="$("$PY" "$SEAT" next-seat chief-of-staff-work-o1)"
printf '%s\n' "$plan3" | grep -q '"session": "cosw-o1-a1"' || fail "next-seat from lane: $plan3"

echo "spawn-always dry-run checks passed"