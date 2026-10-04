#!/usr/bin/env bash
# Shared paths for the browser-eval lab. No host secrets.
set -euo pipefail

_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "${_COMMON_DIR}/.." && pwd)"
STATE_DIR="${BROWSER_EVAL_STATE_DIR:-${HOME}/.local/share/browser-eval}"
CACHE_DIR="${BROWSER_EVAL_CACHE_DIR:-${HOME}/Library/Caches/browser-eval}"
APPS_DIR="${STATE_DIR}/apps"
PROFILES_DIR="${STATE_DIR}/profiles"
ARTIFACTS_DIR="${BROWSER_EVAL_ARTIFACTS_DIR:-${STATE_DIR}/artifacts}"
WORKSPACE_DIR="${BROWSER_EVAL_WORKSPACE_DIR:-${STATE_DIR}/workspace}"
IMAGE="${BROWSER_EVAL_IMAGE:-browser-eval:latest}"
RUNTIME="${BROWSER_EVAL_RUNTIME:-podman}"

DIA_URL="${DIA_URL:-https://releases.diabrowser.com/release/Dia-latest.dmg}"
COMET_URL="${COMET_URL:-https://www.perplexity.ai/rest/browser/download?channel=stable&platform=mac_arm64}"
COMET_FIXTURE="${COMET_FIXTURE:-${HOME}/Downloads/Personal/comet_latest.dmg}"

CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
ARC_APP="${ARC_APP:-/Applications/Arc.app}"
DIA_APP="${DIA_APP:-${APPS_DIR}/Dia.app}"
COMET_APP="${COMET_APP:-${APPS_DIR}/Comet.app}"

ensure_dirs() {
  mkdir -p "$STATE_DIR" "$CACHE_DIR" "$APPS_DIR" "$PROFILES_DIR" "$ARTIFACTS_DIR" "$WORKSPACE_DIR"
}

die() {
  printf 'browser-eval: ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf 'browser-eval: %s\n' "$*" >&2
}
