# sandbox helpers for tmux-connect (sourced; not executable)

sandbox_list_cmd() {
    cat <<'EOF'
if command -v podman >/dev/null 2>&1; then
  podman ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
else
  echo 'tmux-connect: podman not found on host' >&2
  exit 2
fi
EOF
}

sandbox_sessions_cmd() {
    printf 'podman exec %q tmux list-sessions\n' "$1"
}

sandbox_attach_cmd() {
    local sandbox="$1" session="$2" host_label="$3"
    local sb se left
    sb="$(printf '%q' "$sandbox")"
    se="$(printf '%q' "$session")"
    left="'[#S] ${sandbox} @ ${host_label} '"
    cat <<EOF
set -eu
command -v podman >/dev/null || { echo "tmux-connect: podman not found on host" >&2; exit 1; }
podman container exists $sb || { echo "tmux-connect: sandbox not found: $sandbox" >&2; exit 1; }
running=\$(podman inspect -f '{{.State.Running}}' $sb)
[ "\$running" = true ] || { echo "tmux-connect: sandbox not running: $sandbox" >&2; exit 1; }
podman exec $sb sh -lc 'command -v tmux' >/dev/null 2>&1 || { echo "tmux-connect: tmux not found in sandbox $sandbox" >&2; exit 1; }
exec podman exec -it $sb tmux new-session -A -s $se \\; set-option -g status-left-length 80 \\; set-option -g status-left $left
EOF
}

local_sandbox_listing() {
    if ! command -v podman >/dev/null 2>&1; then
        echo "tmux-connect: podman not found" >&2
        return 1
    fi
    podman ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
}

local_sandbox_names() {
    if ! command -v podman >/dev/null 2>&1; then
        return 1
    fi
    podman ps --format '{{.Names}}'
}

cmd_sandbox_ls() {
    local name="${1:-local}"
    local ssh_target listing names status

    if [[ "$name" == "local" || "$name" == "mac" ]]; then
        if ! listing=$(local_sandbox_listing); then
            echo "tmux-connect: no local podman sandboxes" >&2
            return 1
        fi
        if [[ -z "$listing" ]]; then
            echo "tmux-connect: no running sandboxes on $name" >&2
            : | write_sandbox_cache "$name"
            return 0
        fi
        printf '%s\n' "$listing"
        local_sandbox_names | write_sandbox_cache "$name"
        return 0
    fi

    ssh_target=$(get_host_field "$name" "ssh") || {
        echo "Unknown host: $name" >&2
        echo "Run 'tmux-connect --list' to see available hosts" >&2
        return 1
    }

    if [[ "$ssh_target" == "local" ]]; then
        cmd_sandbox_ls local
        return
    fi

    if listing=$(remote_tmux_cmd "$ssh_target" "$(sandbox_list_cmd)"); then
        if [[ -z "$listing" ]]; then
            echo "tmux-connect: no running sandboxes on $name" >&2
            : | write_sandbox_cache "$name"
            return 0
        fi
        printf '%s\n' "$listing"
        printf '%s\n' "$listing" | awk '{print $1}' | write_sandbox_cache "$name"
        return 0
    else
        status=$?
        if [[ "$status" -eq 2 ]]; then
            echo "tmux-connect: no running sandboxes on $name" >&2
            : | write_sandbox_cache "$name"
            return 0
        fi
        echo "tmux-connect: could not list sandboxes on $name" >&2
        return 1
    fi
}

cmd_sandbox_sessions_ls() {
    local name="$1" sandbox="$2"
    local ssh_target listing status

    if ! valid_tmux_ident "$sandbox"; then
        echo "tmux-connect: invalid sandbox name: $sandbox" >&2
        return 2
    fi

    if [[ "$name" == "local" || "$name" == "mac" ]]; then
        if ! listing=$(podman exec "$sandbox" tmux list-sessions 2>/dev/null); then
            echo "tmux-connect: no attachable sessions in $sandbox on $name" >&2
            : | write_sandbox_session_cache "$name" "$sandbox"
            return 0
        fi
        printf '%s\n' "$listing"
        printf '%s\n' "$listing" | awk -F: '{print $1}' | write_sandbox_session_cache "$name" "$sandbox"
        return 0
    fi

    ssh_target=$(get_host_field "$name" "ssh") || {
        echo "Unknown host: $name" >&2
        echo "Run 'tmux-connect --list' to see available hosts" >&2
        return 1
    }

    if listing=$(remote_tmux_cmd "$ssh_target" "$(sandbox_sessions_cmd "$sandbox")"); then
        printf '%s\n' "$listing"
        printf '%s\n' "$listing" | awk -F: '{print $1}' | write_sandbox_session_cache "$name" "$sandbox"
        return 0
    else
        status=$?
        if [[ "$status" -eq 2 ]]; then
            echo "tmux-connect: no attachable sessions in $sandbox on $name" >&2
            : | write_sandbox_session_cache "$name" "$sandbox"
            return 0
        fi
        echo "tmux-connect: could not list sessions in $sandbox on $name" >&2
        return 1
    fi
}

connect_sandbox_local() {
    local sandbox="$1" session="$2" host_label="$3"
    local left
    left="[#S] ${sandbox} @ ${host_label} "
    if ! command -v podman >/dev/null 2>&1; then
        echo "tmux-connect: podman not found" >&2
        return 1
    fi
    if ! podman container exists "$sandbox"; then
        echo "tmux-connect: sandbox not found: $sandbox" >&2
        return 1
    fi
    exec podman exec -it "$sandbox" tmux new-session -A -s "$session" \; \
        set-option -g status-left-length 80 \; \
        set-option -g status-left "$left"
}

connect_sandbox_remote() {
    local ssh_target="$1" sandbox="$2" session="$3" host_label="$4"
    local target status=1 remote_cmd
    local -a targets=()

    remote_cmd="$(sandbox_attach_cmd "$sandbox" "$session" "$host_label")"
    while IFS= read -r target; do
        [[ -n "$target" ]] && targets+=("$target")
    done < <(split_ssh_targets "$ssh_target")

    for target in "${targets[@]}"; do
        if [[ "${#targets[@]}" -gt 1 ]]; then
            echo "Trying SSH target: $target" >&2
        fi
        if ssh -o ConnectTimeout="${TMUX_CONNECT_CONNECT_TIMEOUT:-5}" -t "$target" "$remote_cmd"; then
            return 0
        else
            status=$?
            echo "SSH target failed ($target, exit $status)" >&2
        fi
    done
    return "$status"
}

connect_sandbox() {
    local name="$1"
    local sandbox="$2"
    local session="${3:-home}"
    local ssh_target

    if ! valid_tmux_ident "$sandbox"; then
        echo "tmux-connect: invalid sandbox name: $sandbox" >&2
        return 2
    fi
    if ! valid_tmux_ident "$session"; then
        echo "tmux-connect: invalid session name: $session" >&2
        return 2
    fi

    ssh_target=$(get_host_field "$name" "ssh") || {
        echo "Unknown host: $name"
        echo "Run 'tmux-connect --list' to see available hosts"
        return 1
    }

    echo "Connecting to $name sandbox $sandbox → tmux session: $session"

    if [[ "$ssh_target" == "local" || "$name" == "local" || "$name" == "mac" ]]; then
        connect_sandbox_local "$sandbox" "$session" "$name"
    else
        connect_sandbox_remote "$ssh_target" "$sandbox" "$session" "$name"
    fi
}

sandbox_main() {
    case "${1:-}" in
        -h|--help|help)
            usage
            ;;
        --ls)
            cmd_sandbox_ls "${2:-local}"
            ;;
        --ls-cache)
            cmd_sandbox_ls_cache "${2:-local}" "${3:-}"
            ;;
        "")
            echo "Usage: tmux-connect --sandbox --ls [host]" >&2
            echo "       tmux-connect --sandbox <host> --ls" >&2
            echo "       tmux-connect --sandbox <host> <sandbox> [session]" >&2
            echo "       tmux-connect --sandbox <host> <sandbox> --ls" >&2
            return 2
            ;;
        *)
            if [[ "${2:-}" == "--ls" ]]; then
                cmd_sandbox_ls "$1"
            elif [[ -z "${2:-}" ]]; then
                echo "tmux-connect: sandbox name required (try: tmux-connect --sandbox $1 --ls)" >&2
                return 2
            elif [[ "${3:-}" == "--ls" ]]; then
                cmd_sandbox_sessions_ls "$1" "$2"
            else
                connect_sandbox "$1" "$2" "${3:-home}"
            fi
            ;;
    esac
}
