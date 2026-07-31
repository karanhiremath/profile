# shellcheck shell=bash
# Stage SSH access for Hermes podman sandboxes.
#
# Sandboxes get no SSH context by default: no agent socket, no keys, no config,
# and a container user that differs from the host user. Agent terminal tools
# therefore cannot reach remote hosts -- host key verification fails, then
# publickey auth is denied.
#
# No key material is ever copied into a sandbox. The identity that authenticates
# to our hosts lives in an agent (1Password's agent never writes a private key to
# disk), so a filtering agent relay is used instead -- see
# sandbox-ssh-agent-relay.py. Revoking sandbox access is stopping the relay.
#
# Two container facts drive the layout below:
#
#   1. ssh expands `~` from the container user's passwd entry, not $HOME. In the
#      hermes-agent image that home is /workspace, which is a read-write
#      virtiofs bind-mount from the host, so nothing is staged into a home
#      directory at all.
#   2. /etc/ssh/ssh_config carries `Include /etc/ssh/ssh_config.d/*.conf`, and
#      OpenSSH takes the first value it obtains for each keyword. A drop-in that
#      sorts before the distro's own file therefore wins.
#
# Config and known_hosts are mounted read-only at /etc/hermes-ssh and referenced
# by absolute path from a 40- drop-in, which works regardless of which user the
# agent runs as or what its home is.
#
# Addressing is tailnet-first: HostName is the peer's MagicDNS name, so the
# sandbox needs no VPN, no ProxyJump chain, and no tailscaled of its own.
#
# Deliberately generic: hosts, users and addressing are all derived at runtime
# from the operator's own ~/.ssh/config and `tailscale status`. No hostnames,
# addresses, or org-specific details are baked into this repo.
#
# Scope rule: a tailnet peer is exposed only when the operator's ssh config
# matches it with an explicit (non-`*`) Host pattern, so incidental peers such
# as laptops and phones are left out.

HERMES_SANDBOX_SSH_DIR="${HERMES_SANDBOX_SSH_DIR:-/etc/hermes-ssh}"
HERMES_SANDBOX_SSH_DROPIN="${HERMES_SANDBOX_SSH_DROPIN:-/etc/ssh/ssh_config.d/40-hermes-sandbox.conf}"
# In-container agent socket, and the loopback port the host relay listens on.
HERMES_SANDBOX_SSH_AGENT_SOCK="${HERMES_SANDBOX_SSH_AGENT_SOCK:-/tmp/hermes-ssh-agent.sock}"
HERMES_SANDBOX_SSH_AGENT_PORT="${HERMES_SANDBOX_SSH_AGENT_PORT:-17352}"

hermes_ssh_tailnet_suffix() {
  command -v tailscale >/dev/null 2>&1 || return 1
  tailscale status --json 2>/dev/null \
    | sed -n 's/.*"MagicDNSSuffix"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -n 1
}

hermes_ssh_tailnet_peers() {
  command -v tailscale >/dev/null 2>&1 || return 1
  tailscale status 2>/dev/null | awk 'NF >= 2 && $1 ~ /^100\./ { print $2 }'
}

# Explicit, non-wildcard Host patterns from the operator's ssh config.
hermes_ssh_config_patterns() {
  local cfg="${1:-$HOME/.ssh/config}" line pat
  [ -f "$cfg" ] || return 0
  while IFS= read -r line; do
    case "$line" in
      [Hh][Oo][Ss][Tt]" "*|[Hh][Oo][Ss][Tt]$'\t'*) ;;
      *) continue ;;
    esac
    line="${line#*[Hh][Oo][Ss][Tt]}"
    for pat in $line; do
      [ "$pat" = "*" ] && continue
      printf '%s\n' "$pat"
    done
  done <"$cfg"
}

hermes_ssh_alias_is_configured() {
  local alias="$1" cfg="${2:-$HOME/.ssh/config}" pat
  while IFS= read -r pat; do
    # shellcheck disable=SC2254  # pattern is intentionally a glob
    case "$alias" in $pat) return 0 ;; esac
  done < <(hermes_ssh_config_patterns "$cfg")
  return 1
}

# Emit `key<TAB>value` pairs of the effective ssh config for one alias.
hermes_ssh_effective() {
  ssh -G "$1" 2>/dev/null | awk '{ k = $1; $1 = ""; sub(/^ /, ""); print k "\t" $0 }'
}

# Stage the sandbox SSH tree. Echoes the staged host directory on success.
# Usage: stage_ssh_auth_for_sandbox <profile_home> [relay_script]
stage_ssh_auth_for_sandbox() {
  local profile_home="$1" relay="${2:-}" dst tmp suffix alias staged_hosts=0
  local user port strict hostkeyalias line key f

  [ -n "$profile_home" ] || return 1
  [ -f "$HOME/.ssh/config" ] || return 0
  suffix="$(hermes_ssh_tailnet_suffix)" || return 0
  [ -n "$suffix" ] || return 0

  dst="$profile_home/sandbox-auth/ssh"
  tmp="$profile_home/sandbox-auth/ssh.tmp.$$"
  rm -rf "$tmp"
  mkdir -p "$tmp" || return 1
  chmod 0700 "$tmp"

  {
    printf '# Generated for the Hermes sandbox. Do not edit; regenerated on launch.\n'
    printf '# Tailnet-first addressing: no ProxyJump or VPN is needed in-container.\n'
    printf '# Auth is via the relayed agent socket below; no key material is staged.\n\n'
  } >"$tmp/config"

  while IFS= read -r alias; do
    [ -n "$alias" ] || continue
    hermes_ssh_alias_is_configured "$alias" || continue

    user=""; port=""; strict=""; hostkeyalias=""
    while IFS=$'\t' read -r key line; do
      case "$key" in
        user) user="$line" ;;
        port) port="$line" ;;
        hostkeyalias) hostkeyalias="$line" ;;
        stricthostkeychecking)
          # `ssh -G` renders yes/no as true/false, which are not valid values to
          # write back into a config file. Map them back.
          case "$line" in
            true) strict="yes" ;;
            false) strict="no" ;;
            *) strict="$line" ;;
          esac
          ;;
      esac
    done < <(hermes_ssh_effective "$alias")

    {
      printf 'Host %s\n' "$alias"
      printf '    HostName %s.%s\n' "$alias" "$suffix"
      [ -z "$user" ] || printf '    User %s\n' "$user"
      [ -z "$port" ] || [ "$port" = "22" ] || printf '    Port %s\n' "$port"
      printf '    IdentityAgent %s\n' "$HERMES_SANDBOX_SSH_AGENT_SOCK"
      # Pin the host key to the stable alias, not the rotating tailnet address.
      printf '    HostKeyAlias %s\n' "${hostkeyalias:-$alias}"
      printf '    UserKnownHostsFile %s/known_hosts\n' "$HERMES_SANDBOX_SSH_DIR"
      [ -z "$strict" ] || printf '    StrictHostKeyChecking %s\n' "$strict"
      # ControlMaster sockets cannot be created under a read-only mount, and
      # agent forwarding into a sandboxed shell is never wanted.
      printf '    ControlMaster no\n'
      printf '    ForwardAgent no\n\n'
    } >>"$tmp/config"
    staged_hosts=$((staged_hosts + 1))
  done < <(hermes_ssh_tailnet_peers)

  if [ "$staged_hosts" -eq 0 ]; then
    rm -rf "$tmp"
    return 0
  fi

  # known_hosts is staged read-only and keyed by HostKeyAlias. Always create it
  # so ssh has a file to read even when the host has no entries yet.
  if [ -f "$HOME/.ssh/known_hosts" ]; then
    cp "$HOME/.ssh/known_hosts" "$tmp/known_hosts" 2>/dev/null || : >"$tmp/known_hosts"
  else
    : >"$tmp/known_hosts"
  fi
  if [ -n "$relay" ] && [ -f "$relay" ]; then
    cp "$relay" "$tmp/agent-relay.py" 2>/dev/null || true
    chmod 0444 "$tmp/agent-relay.py" 2>/dev/null || true
  fi
  chmod 0444 "$tmp/known_hosts" "$tmp/config"

  # Preserve the directory inode so existing read-only bind mounts keep seeing
  # refreshed material, matching how the gh/aws/op trees are staged.
  if [ -d "$dst" ]; then
    for f in "$tmp"/*; do
      [ -e "$f" ] || continue
      cp -p "$f" "$dst/$(basename "$f")" 2>/dev/null || true
    done
    rm -rf "$tmp"
  else
    mv "$tmp" "$dst" 2>/dev/null || { rm -rf "$tmp"; return 1; }
  fi
  chmod 0700 "$dst"
  printf '%s\n' "$dst"
}

# Read-only volume arguments for a sandbox launch: "src:dst:ro" lines.
hermes_sandbox_ssh_volumes() {
  local ssh_dir="$1"
  [ -n "$ssh_dir" ] && [ -d "$ssh_dir" ] || return 0
  printf '%s:%s:ro\n' "$ssh_dir" "$HERMES_SANDBOX_SSH_DIR"
  printf '%s/config:%s:ro\n' "$ssh_dir" "$HERMES_SANDBOX_SSH_DROPIN"
}

# Start the host side of the agent relay if it is not already listening.
# Usage: start_host_ssh_agent_relay <profile_home> <relay_script>
start_host_ssh_agent_relay() {
  local profile_home="$1" relay="$2" pidfile logfile pid python
  [ -n "$profile_home" ] || return 1
  [ -n "$relay" ] && [ -f "$relay" ] || return 0
  [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "$SSH_AUTH_SOCK" ] || return 0

  pidfile="$profile_home/sandbox-auth/ssh-agent-relay.pid"
  logfile="$profile_home/logs/ssh-agent-relay.log"
  mkdir -p "$profile_home/sandbox-auth" "$profile_home/logs"

  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  # Another profile may already serve the port. Spawning a second listener would
  # only fail to bind and be respawned on every sync cycle, so stop here.
  if (exec 3<>"/dev/tcp/127.0.0.1/$HERMES_SANDBOX_SSH_AGENT_PORT") 2>/dev/null; then
    exec 3<&- 2>/dev/null || true
    return 0
  fi

  python="$(command -v python3 || true)"
  [ -n "$python" ] || return 0
  nohup "$python" "$relay" --mode host \
    --agent-socket "$SSH_AUTH_SOCK" \
    --port "$HERMES_SANDBOX_SSH_AGENT_PORT" \
    --bind 127.0.0.1 >>"$logfile" 2>&1 &
  printf '%s\n' "$!" >"$pidfile"
}

# Push config into running sandboxes and start their relay side, so no container
# restart is needed. Usage: refresh_running_ssh_auth <podman> <ssh_dir> [label]
refresh_running_ssh_auth() {
  local podman="$1" ssh_dir="$2" label="${3:-}" cid
  [ -n "$podman" ] || return 0
  [ -n "$ssh_dir" ] && [ -d "$ssh_dir" ] || return 0

  local -a filter=()
  [ -z "$label" ] || filter=(--filter "label=$label")

  while IFS= read -r cid; do
    [ -n "$cid" ] || continue
    "$podman" exec -u 0 "$cid" sh -lc 'mkdir -p "$1" "$(dirname "$2")"' \
      _ "$HERMES_SANDBOX_SSH_DIR" "$HERMES_SANDBOX_SSH_DROPIN" >/dev/null 2>&1 || true
    "$podman" cp "$ssh_dir/." "$cid:$HERMES_SANDBOX_SSH_DIR/" >/dev/null 2>&1 || continue
    "$podman" cp "$ssh_dir/config" "$cid:$HERMES_SANDBOX_SSH_DROPIN" >/dev/null 2>&1 || true
    "$podman" exec -u 0 "$cid" sh -lc '
      chmod 0755 "$1" 2>/dev/null || true
      chmod 0444 "$1"/* "$2" 2>/dev/null || true
    ' _ "$HERMES_SANDBOX_SSH_DIR" "$HERMES_SANDBOX_SSH_DROPIN" >/dev/null 2>&1 || true

    # Container side of the relay: unix socket -> host loopback port.
    if ! "$podman" exec "$cid" sh -lc 'test -S "$1"' _ "$HERMES_SANDBOX_SSH_AGENT_SOCK" >/dev/null 2>&1; then
      "$podman" exec -d "$cid" sh -lc \
        'python3 "$1/agent-relay.py" --mode container --listen "$2" --port "$3" >/tmp/hermes-ssh-agent-relay.log 2>&1' \
        _ "$HERMES_SANDBOX_SSH_DIR" "$HERMES_SANDBOX_SSH_AGENT_SOCK" \
        "$HERMES_SANDBOX_SSH_AGENT_PORT" >/dev/null 2>&1 || true
    fi
  done < <("$podman" ps "${filter[@]}" --format '{{.ID}}' 2>/dev/null || true)
}
