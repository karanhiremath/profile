#!/usr/bin/env bash
# Shared paths for the tmux QEMU Omarchy guest on this Mac.
# Official ISO is bootstrap only. Custom ISO is the home-mbp-13 install.
# This is not a Podman stack and never shares the Termix compose.
set -euo pipefail

OMARCHY_TARGET_HOST="${OMARCHY_TARGET_HOST:-home-mbp-13}"
OMARCHY_ISO_VERSION="${OMARCHY_ISO_VERSION:-4.0.3}"
OMARCHY_ISO_URL="${OMARCHY_ISO_URL:-https://iso.omarchy.org/omarchy-${OMARCHY_ISO_VERSION}.iso}"
OMARCHY_ISO_SHA256="${OMARCHY_ISO_SHA256:-03d60bc74306dca51f96e1a84b690871d8d606826b260edd0208962da8507d14}"
OMARCHY_ISO_REPO="${OMARCHY_ISO_REPO:-https://github.com/omacom/omarchy-iso.git}"
OMARCHY_ISO_REF="${OMARCHY_ISO_REF:-quattro}"
OMARCHY_ISO_SRC="${OMARCHY_ISO_SRC:-${HOME}/src/omarchy-iso}"

OMARCHY_CACHE_DIR="${OMARCHY_CACHE_DIR:-${HOME}/Library/Caches/hostctl}"
OMARCHY_STATE_DIR="${OMARCHY_STATE_DIR:-${HOME}/.local/share/hostctl/omarchy}"
OMARCHY_BOOTSTRAP_ISO="${OMARCHY_BOOTSTRAP_ISO:-${OMARCHY_CACHE_DIR}/omarchy-${OMARCHY_ISO_VERSION}.iso}"
OMARCHY_ISO_DIR="${OMARCHY_ISO_DIR:-${OMARCHY_STATE_DIR}/iso}"
OMARCHY_CURRENT_ISO="${OMARCHY_CURRENT_ISO:-${OMARCHY_ISO_DIR}/current.iso}"
OMARCHY_CUSTOM_ISO="${OMARCHY_CUSTOM_ISO:-${OMARCHY_ISO_DIR}/custom/omarchy-${OMARCHY_TARGET_HOST}.iso}"
OMARCHY_CIDATA_ISO="${OMARCHY_CIDATA_ISO:-${OMARCHY_STATE_DIR}/cidata.iso}"
OMARCHY_DISK="${OMARCHY_DISK:-${OMARCHY_STATE_DIR}/disks/${OMARCHY_TARGET_HOST}.qcow2}"
OMARCHY_DISK_GIB="${OMARCHY_DISK_GIB:-40}"
OMARCHY_OVMF_CODE="${OMARCHY_OVMF_CODE:-/opt/homebrew/share/qemu/edk2-x86_64-code.fd}"
OMARCHY_OVMF_VARS="${OMARCHY_OVMF_VARS:-${OMARCHY_STATE_DIR}/firmware/edk2-vars.fd}"
OMARCHY_QMP="${OMARCHY_QMP:-${OMARCHY_STATE_DIR}/qmp.sock}"
OMARCHY_PIDFILE="${OMARCHY_PIDFILE:-${OMARCHY_STATE_DIR}/qemu.pid}"
OMARCHY_TMUX_SESSION="${OMARCHY_TMUX_SESSION:-oma-qemu}"
OMARCHY_MEM_MIB="${OMARCHY_MEM_MIB:-4096}"
OMARCHY_SMP="${OMARCHY_SMP:-4}"

OMARCHY_SSH_USER="${OMARCHY_SSH_USER:-karan}"
OMARCHY_SSH_HOST="${OMARCHY_SSH_HOST:-127.0.0.1}"
OMARCHY_SSH_PORT="${OMARCHY_SSH_PORT:-2222}"
OMARCHY_TAILNET_FQDN="${OMARCHY_TAILNET_FQDN:-try-omarchy.tail1e8436.ts.net}"
OMARCHY_SHARE_DIR="${OMARCHY_SHARE_DIR:-${HOME}/src}"
OMARCHY_HOST_DIR="${OMARCHY_HOST_DIR:-${OMARCHY_SHARE_DIR}/.omarchy-host}"
OMARCHY_OP_SSH_AGENT="${OMARCHY_OP_SSH_AGENT:-${HOME}/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock}"
OMARCHY_OP_KEYCHAIN="${OMARCHY_OP_KEYCHAIN:-${PROFILE_DIR:-${HOME}/src/profile}/bin/op-keychain/op-keychain}"
OMARCHY_HAUTH="${OMARCHY_HAUTH:-${PROFILE_DIR:-${HOME}/src/profile}/bin/hauth/hauth}"
OMARCHY_OP_KEYCHAIN_SSH_ALIASES="${OMARCHY_OP_KEYCHAIN_SSH_ALIASES:-ssh.termix.login ssh.termix.hostctl ssh.termix.iphone-hostctl}"
OMARCHY_SSH_CONFIG="${OMARCHY_SSH_CONFIG:-${HOME}/.ssh/config}"
OMARCHY_SSH_CONFIG_BEGIN="# BEGIN hostctl-try-omarchy"
OMARCHY_SSH_CONFIG_END="# END hostctl-try-omarchy"
OMARCHY_ENV_FILE="${OMARCHY_ENV_FILE:-${HOME}/.local/share/hostctl/omarchy.env}"

# Legacy Try Omarchy.app paths. destroy still removes these if they reappear.
OMARCHY_APP="${OMARCHY_APP:-/Applications/Try Omarchy.app}"
OMARCHY_APP_SUPPORT="${OMARCHY_APP_SUPPORT:-${HOME}/Library/Application Support/Try Omarchy}"
OMARCHY_APP_PREFS="${OMARCHY_APP_PREFS:-${HOME}/Library/Preferences/dev.tryomarchy.native.plist}"

omarchy_load_local_env() {
    local file="${OMARCHY_ENV_FILE}"
    [ -f "$file" ] || return 0
    python3 - "$file" <<'PY'
import os
import sys
from pathlib import Path

allowed = {
    "OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF",
    "OMARCHY_OP_ACCOUNT",
    "OMARCHY_OP_SSH_VAULT",
    "OMARCHY_OP_CLI",
    "OMARCHY_SSH_USER",
    "OMARCHY_SSH_HOST",
    "OMARCHY_SSH_PORT",
    "OMARCHY_ISO_PASSWORD_HASH",
}
for raw in Path(sys.argv[1]).read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key not in allowed or key in os.environ:
        continue
    value = value.strip().strip("'").strip('"')
    print(f"{key}={value}")
PY
}

while IFS= read -r _omarchy_env_line; do
    case "${_omarchy_env_line}" in
        OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF=*|OMARCHY_OP_ACCOUNT=*|OMARCHY_OP_SSH_VAULT=*|OMARCHY_OP_CLI=*|OMARCHY_SSH_USER=*|OMARCHY_SSH_HOST=*|OMARCHY_SSH_PORT=*|OMARCHY_ISO_PASSWORD_HASH=*)
            export "${_omarchy_env_line}"
            ;;
    esac
done < <(omarchy_load_local_env)
unset _omarchy_env_line
OMARCHY_OP_CLI="${OMARCHY_OP_CLI:-op}"
OMARCHY_OP_ACCOUNT="${OMARCHY_OP_ACCOUNT:-my.1password.com}"
OMARCHY_OP_SSH_VAULT="${OMARCHY_OP_SSH_VAULT:-Personal}"
OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF="${OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF:-}"
OMARCHY_ISO_PASSWORD_HASH="${OMARCHY_ISO_PASSWORD_HASH:-}"

omarchy_log() { printf 'omarchy: %s\n' "$*" >&2; }

omarchy_die() {
    omarchy_log "ERROR: $*"
    exit 1
}

omarchy_qemu_bin() {
    command -v qemu-system-x86_64 || true
}

omarchy_qemu_img() {
    command -v qemu-img || true
}

omarchy_qemu_running() {
    if [ -f "$OMARCHY_PIDFILE" ]; then
        local pid
        pid="$(cat "$OMARCHY_PIDFILE" 2>/dev/null || true)"
        if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    pgrep -f "qemu-system-x86_64.*${OMARCHY_TARGET_HOST}" >/dev/null 2>&1
}

omarchy_iso_kind() {
    if [ -L "$OMARCHY_CURRENT_ISO" ]; then
        local dest
        dest="$(readlink "$OMARCHY_CURRENT_ISO")"
        case "$dest" in
            *custom*) printf 'custom\n' ;;
            *) printf 'bootstrap\n' ;;
        esac
        return
    fi
    if [ -f "$OMARCHY_CURRENT_ISO" ]; then
        printf 'file\n'
        return
    fi
    printf 'missing\n'
}

omarchy_free_gib() {
    python3 - <<'PY'
import shutil
free = shutil.disk_usage("/System/Volumes/Data").free
print(f"{free / (1024 ** 3):.1f}")
PY
}
