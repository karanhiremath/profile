#!/usr/bin/env bash
# tmux + QEMU lifecycle for the home-mbp-13 Omarchy guest.
set -euo pipefail

omarchy_ensure_dirs() {
    mkdir -p "$OMARCHY_CACHE_DIR" "$OMARCHY_ISO_DIR/custom" \
        "$(dirname "$OMARCHY_DISK")" "$(dirname "$OMARCHY_OVMF_VARS")" \
        "$OMARCHY_STATE_DIR"
}

omarchy_ensure_disk() {
    omarchy_ensure_dirs
    if [ -f "$OMARCHY_DISK" ]; then
        return 0
    fi
    local img
    img="$(omarchy_qemu_img)"
    [ -n "$img" ] || omarchy_die "qemu-img is not on PATH; brew install qemu"
    omarchy_log "creating ${OMARCHY_DISK} (${OMARCHY_DISK_GIB}G sparse)"
    "$img" create -f qcow2 "$OMARCHY_DISK" "${OMARCHY_DISK_GIB}G" >/dev/null
}

omarchy_ensure_firmware() {
    omarchy_ensure_dirs
    [ -f "$OMARCHY_OVMF_CODE" ] || omarchy_die "missing ${OMARCHY_OVMF_CODE}; brew install qemu"
    if [ ! -f "$OMARCHY_OVMF_VARS" ]; then
        omarchy_log "seeding OVMF vars ${OMARCHY_OVMF_VARS}"
        local template="${OMARCHY_OVMF_CODE%/*}/edk2-i386-vars.fd"
        if [ -f "$template" ]; then
            cp "$template" "$OMARCHY_OVMF_VARS"
        else
            dd if=/dev/zero of="$OMARCHY_OVMF_VARS" bs=1m count=2 >/dev/null 2>&1
        fi
    fi
}

omarchy_qemu_up() {
    if omarchy_qemu_running; then
        omarchy_log "already running (tmux ${OMARCHY_TMUX_SESSION})"
        return 0
    fi
    if tmux has-session -t "$OMARCHY_TMUX_SESSION" 2>/dev/null; then
        omarchy_log "reaping stale tmux session ${OMARCHY_TMUX_SESSION}"
        tmux kill-session -t "$OMARCHY_TMUX_SESSION"
    fi
    omarchy_ensure_disk
    omarchy_ensure_firmware
    [ -e "$OMARCHY_CURRENT_ISO" ] || omarchy_die "no current ISO; run hostctl omarchy iso fetch"
    omarchy_log "starting qemu in tmux session ${OMARCHY_TMUX_SESSION}"
    tmux new-session -d -s "$OMARCHY_TMUX_SESSION" -n qemu \
        "${SCRIPT_DIR}/qemu-run"
    local i
    for i in 1 2 3 4 5 6 7 8 9 10; do
        omarchy_qemu_running && return 0
        sleep 0.3
    done
    omarchy_die "qemu did not stay up; tmux attach -t ${OMARCHY_TMUX_SESSION}"
}

omarchy_qemu_down() {
    if ! omarchy_qemu_running && ! tmux has-session -t "$OMARCHY_TMUX_SESSION" 2>/dev/null; then
        omarchy_log "not running"
        rm -f "$OMARCHY_PIDFILE" "$OMARCHY_QMP"
        return 0
    fi
    if [ -S "$OMARCHY_QMP" ]; then
        python3 - "$OMARCHY_QMP" <<'PY' >/dev/null 2>&1 || true
import json, socket, sys
path = sys.argv[1]
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(3)
try:
    sock.connect(path)
    sock.recv(4096)
    sock.sendall(b'{"execute":"qmp_capabilities"}\n')
    sock.recv(4096)
    sock.sendall(b'{"execute":"system_powerdown"}\n')
    sock.recv(4096)
except OSError:
    pass
finally:
    sock.close()
PY
        local i
        for i in 1 2 3 4 5 6 7 8 9 10; do
            omarchy_qemu_running || break
            sleep 1
        done
    fi
    if omarchy_qemu_running; then
        local pid
        pid="$(cat "$OMARCHY_PIDFILE" 2>/dev/null || true)"
        if [ -n "${pid:-}" ]; then
            kill "$pid" 2>/dev/null || true
        fi
        pkill -f "qemu-system-x86_64.*${OMARCHY_TARGET_HOST}" 2>/dev/null || true
    fi
    tmux has-session -t "$OMARCHY_TMUX_SESSION" 2>/dev/null \
        && tmux kill-session -t "$OMARCHY_TMUX_SESSION" || true
    rm -f "$OMARCHY_PIDFILE" "$OMARCHY_QMP"
    omarchy_log "stopped"
}

omarchy_qemu_console() {
    tmux has-session -t "$OMARCHY_TMUX_SESSION" 2>/dev/null \
        || omarchy_die "no tmux session ${OMARCHY_TMUX_SESSION}; hostctl omarchy up"
    exec tmux attach -t "$OMARCHY_TMUX_SESSION"
}
