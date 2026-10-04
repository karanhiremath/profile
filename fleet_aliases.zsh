# fleet_aliases.zsh — short, memorable lane aliases. zsh only, by design.
# Source from ~/.zshrc. Everything writes structured stdout so it pipes cleanly.
FLEET_BIN="${FLEET_BIN:-$HOME/src/profile/bin/fleet/fleet}"

fu()  { "$FLEET_BIN" up "$@" }            # fleet up      — bring lanes up
fui() { "$FLEET_BIN" up --infra }         # fleet up infra
fls() { "$FLEET_BIN" ls }                 # fleet list    — tsv, pipe it
fw()  { "$FLEET_BIN" attach "${1:?lane}" } # fleet work   — attach the workflow session
fp()  { "$FLEET_BIN" plan   "${1:?lane}" } # fleet plan   — attach the coordination session
fst() { local t=${1:?target}; shift; "$FLEET_BIN" steer "$t" "$@" }   # fleet steer
fdn() { "$FLEET_BIN" down "${1:?lane}" }  # fleet down

# fleet dispatch — point a pi worker at a spec FILE, never an inline string
fd() {
  local t=${1:?target} spec=${2:?spec path}
  [[ -r $spec ]] || { print -u2 "fd: unreadable spec: $spec"; return 1 }
  "$FLEET_BIN" steer "$t" "Read $spec and execute it"
}

# fleet grep — which lanes are running what:  fg2 claude
fg2() { fls | grep -i -- "${1:?pattern}" }

# fleet count — panes per lane, sorted
fcnt() { fls | cut -f1 | sort | uniq -c | sort -rn }
