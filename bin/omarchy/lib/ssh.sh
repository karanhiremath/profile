#!/usr/bin/env bash
# Publish this Mac's 1Password SSH public keys into the QEMU Omarchy guest.
# Does not bake keys into the factory image. Public keys only.
set -euo pipefail

omarchy_ssh_target() {
    printf '%s@%s' "$OMARCHY_SSH_USER" "$OMARCHY_SSH_HOST"
}

omarchy_ssh_agent_env() {
    if [ -S "$OMARCHY_OP_SSH_AGENT" ]; then
        printf '%s' "$OMARCHY_OP_SSH_AGENT"
        return 0
    fi
    if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "${SSH_AUTH_SOCK}" ]; then
        printf '%s' "$SSH_AUTH_SOCK"
        return 0
    fi
    return 1
}

omarchy_filter_pubkey_lines() {
    awk '/^ssh-(ed25519|rsa|sk-ssh-ed25519) / {print}'
}

omarchy_op_signed_in() {
    command -v "${OMARCHY_OP_CLI}" >/dev/null 2>&1 || return 1
    omarchy_op_env whoami >/dev/null 2>&1
}

omarchy_op_env() {
    OP_ACCOUNT="${OMARCHY_OP_ACCOUNT}" "${OMARCHY_OP_CLI}" "$@"
}

omarchy_op_read_keys() {
    omarchy_op_env read "$OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF" | omarchy_filter_pubkey_lines
}

omarchy_op_extract_item_pubkeys() {
    python3 - <<'PY'
import json, sys
item = json.load(sys.stdin)
for field in item.get("fields") or []:
    value = (field.get("value") or "").strip()
    if value.startswith("ssh-ed25519 ") or value.startswith("ssh-rsa ") or value.startswith("sk-ssh-ed25519 "):
        print(value)
PY
}

omarchy_op_vault_public_keys() {
    local ids id json
    ids="$(omarchy_op_env item list --categories "SSH Key" --vault "$OMARCHY_OP_SSH_VAULT" --format json \
        | python3 -c 'import json,sys; print("\n".join(i.get("id","") for i in json.load(sys.stdin) if i.get("id")))')" \
        || return 1
    [ -n "$ids" ] || return 0
    while IFS= read -r id; do
        [ -n "$id" ] || continue
        json="$(omarchy_op_env item get "$id" --format json)" || {
            omarchy_log "op item get skipped: ${id}"
            continue
        }
        printf '%s\n' "$json" | omarchy_op_extract_item_pubkeys
    done <<<"$ids"
}

omarchy_agent_public_keys() {
    local sock
    sock="$(omarchy_ssh_agent_env)" || return 1
    SSH_AUTH_SOCK="$sock" ssh-add -L | omarchy_filter_pubkey_lines
}

omarchy_disk_public_keys() {
    local dir="${HOSTCTL_STATE_DIR:-${HOME}/.local/share/hostctl}/termix-master"
    local f
    for f in "${dir}/id_ed25519.pub" "${dir}/iphone-17-pro.pub" "${dir}/termix-login.pub"; do
        [ -f "$f" ] || continue
        omarchy_filter_pubkey_lines <"$f"
    done
}

omarchy_op_keychain_public_keys() {
    local okc hauth dest alias pub
    okc="${OMARCHY_OP_KEYCHAIN}"
    hauth="${OMARCHY_HAUTH}"
    [ -x "$okc" ] || return 1
    dest="$(mktemp "${TMPDIR:-/tmp}/omarchy-okc.XXXXXX")"
    for alias in ${OMARCHY_OP_KEYCHAIN_SSH_ALIASES}; do
        if [ -x "$hauth" ]; then
            if ! "$hauth" unwrap-or-get "$alias" >"$dest" 2>/dev/null; then
                continue
            fi
        elif ! "$okc" get "$alias" >"$dest" 2>/dev/null; then
            continue
        fi
        chmod 600 "$dest"
        pub="$(ssh-keygen -y -f "$dest" 2>/dev/null)" || continue
        printf '%s op-keychain:%s\n' "$(printf '%s' "$pub" | awk '{print $1" "$2}')" "$alias"
    done
    rm -f "$dest"
}

omarchy_ssh_public_keys() {
    local agent_keys="" vault_keys="" ref_keys="" disk_keys="" keychain_keys=""
    keychain_keys="$(omarchy_op_keychain_public_keys)" || keychain_keys=""
    if [ -n "$keychain_keys" ]; then
        omarchy_log "using op-keychain public keys (passwordless agent store)"
    fi
    disk_keys="$(omarchy_disk_public_keys)" || disk_keys=""
    if [ -n "$disk_keys" ]; then
        omarchy_log "using hostctl public keys on disk"
    fi
    if [ "${OMARCHY_SYNC_OP_VAULT:-0}" = "1" ]; then
        if agent_keys="$(omarchy_agent_public_keys)"; then
            :
        else
            agent_keys=""
            omarchy_log "1Password SSH agent unavailable"
        fi
        if omarchy_op_signed_in; then
            vault_keys="$(omarchy_op_vault_public_keys)" \
                || omarchy_die "failed to list SSH keys in vault ${OMARCHY_OP_SSH_VAULT}"
            omarchy_log "op vault ${OMARCHY_OP_SSH_VAULT}: synced SSH Key public keys"
            if [ -n "${OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF}" ]; then
                ref_keys="$(omarchy_op_read_keys)" \
                    || omarchy_die "op read failed for ${OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF}"
                omarchy_log "op read ${OMARCHY_SSH_AUTHORIZED_KEYS_OP_REF}"
            fi
        else
            omarchy_log "op CLI skipped (bind uses op-keychain; set OMARCHY_SYNC_OP_VAULT=1 after eval \$(op signin))"
        fi
    fi
    {
        printf '%s\n' "$keychain_keys"
        printf '%s\n' "$disk_keys"
        printf '%s\n' "$agent_keys"
        printf '%s\n' "$vault_keys"
        printf '%s\n' "$ref_keys"
    } | awk 'NF && !seen[$1" "$2]++'
}

omarchy_write_host_dir() {
    local keys_file script_file keys
    keys="$(omarchy_ssh_public_keys)"
    [ -n "$keys" ] || omarchy_die "no public keys from op-keychain or on-disk hostctl keys"
    mkdir -p "$OMARCHY_HOST_DIR"
    chmod 755 "$OMARCHY_HOST_DIR"
    keys_file="${OMARCHY_HOST_DIR}/authorized_keys"
    script_file="${OMARCHY_HOST_DIR}/install-authorized-keys.sh"
    {
        printf '# Public keys from op-keychain (ssh.termix.*). Synced by omarchy bind.\n'
        printf '%s\n' "$keys"
    } >"$keys_file"
    chmod 644 "$keys_file"
    cat >"$script_file" <<'GUEST'
#!/bin/bash
# Run inside the Omarchy guest. Installs host 1Password public keys.
set -euo pipefail
candidates=(
    "${HOME}/src/.omarchy-host/authorized_keys"
    "/mnt/mac/.omarchy-host/authorized_keys"
)
src=""
for path in "${candidates[@]}"; do
    if [[ -f $path ]]; then
        src=$path
        break
    fi
done
if [[ -z $src ]]; then
    echo "omarchy: no host authorized_keys at ~/src or /mnt/mac" >&2
    exit 1
fi
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
touch "${HOME}/.ssh/authorized_keys"
chmod 600 "${HOME}/.ssh/authorized_keys"
added=0
while IFS= read -r key; do
    [[ -z $key || $key == \#* ]] && continue
    if grep -qxF "$key" "${HOME}/.ssh/authorized_keys"; then
        continue
    fi
    printf '%s\n' "$key" >>"${HOME}/.ssh/authorized_keys"
    added=$((added + 1))
done <"$src"
echo "omarchy: authorized_keys updated from ${src} (+${added})"
GUEST
    chmod 755 "$script_file"
}

omarchy_publish_guest_helpers() {
    local dir="${SCRIPT_DIR}/guest"
    [ -f "${dir}/fix-sshd.sh" ] || omarchy_die "missing ${dir}/fix-sshd.sh"
    [ -f "${dir}/bind-guest.sh" ] || omarchy_die "missing ${dir}/bind-guest.sh"
    mkdir -p "$OMARCHY_HOST_DIR"
    chmod 755 "$OMARCHY_HOST_DIR"
    cp "${dir}/fix-sshd.sh" "${OMARCHY_HOST_DIR}/fix-sshd.sh"
    cp "${dir}/bind-guest.sh" "${OMARCHY_HOST_DIR}/bind-guest.sh"
    chmod 755 "${OMARCHY_HOST_DIR}/fix-sshd.sh" "${OMARCHY_HOST_DIR}/bind-guest.sh"
}

omarchy_upsert_ssh_config() {
    python3 - "$OMARCHY_SSH_CONFIG" "$OMARCHY_SSH_CONFIG_BEGIN" "$OMARCHY_SSH_CONFIG_END" \
        "$OMARCHY_SSH_USER" "$OMARCHY_SSH_HOST" "$OMARCHY_SSH_PORT" "$OMARCHY_TAILNET_FQDN" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
begin, end, user, host, port, fqdn = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]
block = (
    f"{begin}\n"
    f"Host {fqdn}\n"
    f"    HostName {fqdn}\n"
    f"    Port 22\n"
    f"    User {user}\n"
    f"\n"
    f"Host try-omarchy try-omarchy-qemu try-omarchy-hvf\n"
    f"    HostName {host}\n"
    f"    Port {port}\n"
    f"    User {user}\n"
    f"{end}\n"
)
text = path.read_text() if path.exists() else ""
if begin in text and end in text:
    pre, rest = text.split(begin, 1)
    _, post = rest.split(end, 1)
    text = pre.rstrip("\n") + "\n\n" + block + post.lstrip("\n")
else:
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    text += block
path.parent.mkdir(mode=0o700, exist_ok=True)
path.write_text(text)
os.chmod(path, 0o600)
PY
}

omarchy_print_ssh_copy_id() {
    cat <<EOF
Host-owned bind (no guest terminal):
  hostctl omarchy bind
  attach oma-default
  attach oma-s
Prefer MagicDNS: ssh ${OMARCHY_TAILNET_FQDN}
QEMU fallback:   ssh try-omarchy
EOF
}

omarchy_probe_forward() {
    python3 - "$OMARCHY_SSH_HOST" "$OMARCHY_SSH_PORT" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
sock = socket.socket()
sock.settimeout(3)
try:
    sock.connect((host, port))
    data = sock.recv(256)
    if data.startswith(b"SSH-"):
        print("ssh-banner")
    elif data:
        print("connected-no-banner")
    else:
        print("connected-empty")
except TimeoutError:
    print("banner-timeout")
except OSError as exc:
    print(f"unreachable:{exc.strerror}")
finally:
    sock.close()
PY
}

omarchy_setup_ssh() {
    omarchy_write_host_dir
    omarchy_publish_guest_helpers
    omarchy_upsert_ssh_config
    omarchy_log "published op-keychain public keys to ${OMARCHY_HOST_DIR}/authorized_keys"
    omarchy_log "ssh config: ${OMARCHY_TAILNET_FQDN}:22 (prefer) and try-omarchy -> $(omarchy_ssh_target):${OMARCHY_SSH_PORT} (QEMU)"
    echo
    omarchy_print_ssh_copy_id
}

omarchy_qmp_socket() {
    if [ -S "${OMARCHY_QMP:-}" ]; then
        printf '%s\n' "$OMARCHY_QMP"
        return 0
    fi
    python3 - <<'PY'
from pathlib import Path
cands = sorted(Path("/tmp").glob("omarchy-qemu-gpu.*/qmp.sock"), key=lambda p: p.stat().st_mtime, reverse=True)
print(cands[0] if cands else "")
PY
}

omarchy_qmp_bind_guest() {
    local sock script
    sock="$(omarchy_qmp_socket)"
    [ -n "$sock" ] || return 1
    script="/mnt/mac/.omarchy-host/bind-guest.sh"
    python3 - "$sock" "$script" <<'PY'
import json, socket, sys, time

def recv_obj(sock):
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        try:
            return json.loads(buf.decode())
        except json.JSONDecodeError:
            continue
    return None

def send(sock, payload):
    sock.sendall((json.dumps(payload) + "\n").encode())
    return recv_obj(sock)

path, script = sys.argv[1], sys.argv[2]
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(8)
sock.connect(path)
recv_obj(sock)
caps = send(sock, {"execute": "qmp_capabilities"})
if caps and caps.get("error"):
    print(f"qmp-error:{caps['error'].get('desc', caps['error'])}")
    raise SystemExit(1)
info = send(sock, {"execute": "guest-info"})
if not info or info.get("error"):
    print("qmp-no-guest-agent")
    raise SystemExit(2)
ran = send(sock, {
    "execute": "guest-exec",
    "arguments": {
        "path": "/bin/bash",
        "arg": [script],
        "capture-output": True,
    },
})
if not ran or ran.get("error"):
    print(f"qmp-exec-error:{(ran or {}).get('error')}")
    raise SystemExit(3)
pid = ((ran.get("return") or {}).get("pid"))
print(f"qmp-exec:{pid}")
raise SystemExit(0)
PY
}

omarchy_bind() {
    local probe qmp
    omarchy_setup_ssh
    probe="$(omarchy_probe_forward)"
    omarchy_log "QEMU ${OMARCHY_SSH_HOST}:${OMARCHY_SSH_PORT} probe: ${probe}"
    if [ "$probe" != "ssh-banner" ]; then
        if qmp="$(omarchy_qmp_bind_guest 2>/dev/null)"; then
            omarchy_log "QMP guest-exec: ${qmp}"
            sleep 2
            probe="$(omarchy_probe_forward)"
            omarchy_log "QEMU probe after QMP: ${probe}"
        else
            omarchy_log "QMP guest-exec unavailable (${qmp:-no-socket})"
            omarchy_log "offline inject: rebuild cidata (hostctl omarchy iso build) or use the qemu console"
        fi
    fi
    cat <<EOF

Post-reset bind (rerun after every factory reset)
  share:   ${OMARCHY_HOST_DIR}/{authorized_keys,bind-guest.sh,fix-sshd.sh}
  keys:    op-keychain ${OMARCHY_OP_KEYCHAIN_SSH_ALIASES}
  prefer:  ssh ${OMARCHY_TAILNET_FQDN}
  qemu:    ssh try-omarchy   # ${OMARCHY_SSH_HOST}:${OMARCHY_SSH_PORT}
  aliases: oma / oma-default = VM instance tmux; oma-s / mac-s = sandbox tmux

If the SSH banner hangs (probe=${probe}), bind already tried QMP. Rebuild
cidata authorized_keys (hostctl omarchy iso build) or use hostctl omarchy
console. Do not treat the qemu curses window as the bind SOP.
EOF
}

omarchy_inject_ssh_disk() {
    omarchy_die "offline ext4 inject was for Try Omarchy.app. Use hostctl omarchy iso build (cidata authorized_keys) or hostctl omarchy bind"
}

omarchy_print_keys() {
    omarchy_ssh_public_keys
}

omarchy_ssh() {
    exec ssh -p "$OMARCHY_SSH_PORT" "$(omarchy_ssh_target)" "$@"
}
