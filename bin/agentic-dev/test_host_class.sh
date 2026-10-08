#!/usr/bin/env bash
# Host-class + provision dry-run checks. No network, no host CLI installs.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

class_for() {
  env "$@" "$DIR/host-env.sh" --class
}

json_for() {
  env "$@" "$DIR/host-env.sh" --json
}

[ "$(class_for AGENTIC_HOST_CLASS=personal)" = personal ] || fail "override personal"
[ "$(class_for AGENTIC_HOST_CLASS=work)" = work ] || fail "override work"
[ "$(class_for AGENTIC_HOSTNAME=home-mac-mini AGENTIC_KH_DIR=/tmp/no-kh-$$)" = personal ] || fail "mini hostname"
[ "$(class_for AGENTIC_HOSTNAME=karans-macbook-pro-1)" = work ] || fail "mbp hostname"

personal_json="$(json_for AGENTIC_HOST_CLASS=personal)"
printf '%s\n' "$personal_json" | grep -q '"class": "personal"' || fail "json personal class"
printf '%s\n' "$personal_json" | grep -q krop || true
printf '%s\n' "$personal_json" | grep -q /src/karan.hiremath/ && fail "personal json leaked KH path"
printf '%s\n' "$personal_json" | grep -q /hermes/profiles || fail "personal missing hermes profiles"

work_json="$(json_for AGENTIC_HOST_CLASS=work)"
printf '%s\n' "$work_json" | grep -q '"plane": "work"' || fail "json work plane"
printf '%s\n' "$work_json" | grep -q /src/karan.hiremath/ || fail "work json missing KH path"
printf '%s\n' "$work_json" | grep -q /src/hermes/projects && fail "work registry leaked personal hermes projects"

"$DIR/provision" --dry-run --mode host >/dev/null
AGENTIC_HOST_CLASS=personal "$DIR/provision" --dry-run --mode sandbox --project krop-tf >/dev/null
AGENTIC_HOST_CLASS=work "$DIR/provision" --dry-run --mode sandbox --project krop-tf >/dev/null && fail "work sandbox accepted krop" || true

if AGENTIC_HOST_CLASS=personal "$DIR/provision" --dry-run --mode sandbox --project fips-e2e-python314 >/dev/null 2>&1; then
  fail "personal sandbox accepted a work project"
fi

"$DIR/../atop/install" --help >/dev/null
"$DIR/install" --help >/dev/null
"$DIR/../krop" help >/dev/null

sandbox_default() {
  env "$@" bash -c '
    . "$1/host-env.sh"
    default_profile() {
      if [ "${AGENTIC_HOST_CLASS:-}" = personal ]; then
        printf "chief-of-staff\n"
        return
      fi
      case "${AGENTIC_HOSTNAME:-$(hostname -s)}" in
        khire-mac-mini|home-mac-mini|home-mbp-13) printf "chief-of-staff\n" ;;
        *) printf "chief-of-staff-work\n" ;;
      esac
    }
    default_profile
  ' _ "$DIR"
}

[ "$(sandbox_default AGENTIC_HOST_CLASS=personal AGENTIC_HOSTNAME=home-mac-mini)" = chief-of-staff ] || fail "sandbox-ctl personal home-mac-mini"
[ "$(sandbox_default AGENTIC_HOST_CLASS=work AGENTIC_HOSTNAME=karans-macbook-pro-1)" = chief-of-staff-work ] || fail "sandbox-ctl work default"

printf 'ok\n'
