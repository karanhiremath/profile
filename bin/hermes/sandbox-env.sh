# shellcheck shell=sh
# Hermes sandbox activation for local mac/tmux entrypoint.
# Source this before launching herm/hermes so agent state, sessions, tools, and
# terminal/file execution use the isolated profile home below.

export HERMES_SANDBOX_PROFILE="${HERMES_SANDBOX_PROFILE:-herm-sandbox}"
export HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes/profiles/${HERMES_SANDBOX_PROFILE}}"
export HERMES_PROFILE="${HERMES_PROFILE:-${HERMES_SANDBOX_PROFILE}}"
export HERMES_TOOLCHAIN="${HERMES_TOOLCHAIN:-${HOME}/.local/share/hermes-toolchain}"
export TERMINAL_ENV="${HERMES_TERMINAL_ENV:-docker}"
export TERMINAL_CWD="${TERMINAL_CWD:-/workspace}"
export TERMINAL_DOCKER_IMAGE="${TERMINAL_DOCKER_IMAGE:-${HERMES_SANDBOX_IMAGE:-localhost/hermes-agent/python-node:dev}}"
export TERMINAL_SINGULARITY_IMAGE="${TERMINAL_SINGULARITY_IMAGE:-docker://${TERMINAL_DOCKER_IMAGE}}"
export TERMINAL_MODAL_IMAGE="${TERMINAL_MODAL_IMAGE:-${TERMINAL_DOCKER_IMAGE}}"
export TERMINAL_DAYTONA_IMAGE="${TERMINAL_DAYTONA_IMAGE:-${TERMINAL_DOCKER_IMAGE}}"
export TERMINAL_DOCKER_RUN_AS_HOST_USER="${TERMINAL_DOCKER_RUN_AS_HOST_USER:-true}"
export TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES="${TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES:-true}"
export TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE="${TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE:-false}"
export HERMES_COMPOSE_STACK="${HERMES_COMPOSE_STACK:-hermes-sandboxes}"
export HERMES_SANDBOX_NETWORK="${HERMES_SANDBOX_NETWORK:-hermes-sandboxes_default}"
export HERMES_GIT_SYNC_CONTROLLER_HOST="${HERMES_GIT_SYNC_CONTROLLER_HOST:-hermes-git-sync-controller}"
export HERMES_GIT_SYNC_CONTROLLER_MODE="${HERMES_GIT_SYNC_CONTROLLER_MODE:-sidecar-commit-host-cron-push}"
export HERMES_GIT_SYNC_REQUEST_DIR="${HERMES_GIT_SYNC_REQUEST_DIR:-/hermes-control/git-sync/requests}"
export HERMES_GIT_SYNC_STATUS_DIR="${HERMES_GIT_SYNC_STATUS_DIR:-/hermes-control/git-sync/status}"
case "${HERMES_PROFILE}" in
  *-sandbox|hs-*) _hermes_container_hostname="${HERMES_PROFILE}" ;;
  *) _hermes_container_hostname="${HERMES_PROFILE}-sandbox" ;;
esac
export TERMINAL_DOCKER_EXTRA_ARGS="${TERMINAL_DOCKER_EXTRA_ARGS:-[\"--hostname\",\"${_hermes_container_hostname}\"]}"
unset _hermes_container_hostname

# Prefer Podman/Docker-backed Hermes terminal execution. Podman on macOS exposes
# the Docker API via a per-machine socket that is not always the default path.
if [ -z "${DOCKER_HOST:-}" ] && command -v podman >/dev/null 2>&1; then
  _podman_socket="$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null | head -n 1 || true)"
  if [ -n "${_podman_socket}" ] && [ -S "${_podman_socket}" ]; then
    export DOCKER_HOST="unix://${_podman_socket}"
  fi
  unset _podman_socket
fi

# The hermes launcher picks the first python3 on PATH. Keep the Hermes venv
# ahead of Homebrew/system Python so `hermes` resolves hermes_cli correctly.
_hermes_path_prepend() {
  case ":${PATH}:" in
    *":$1:"*) ;;
    *) PATH="$1:${PATH}" ;;
  esac
}

_hermes_path_prepend "${HERMES_TOOLCHAIN}/venv/bin"
_hermes_path_prepend "${HERMES_TOOLCHAIN}/pnpm"
_hermes_path_prepend "${HERMES_TOOLCHAIN}/bun/bin"
export PATH

unset -f _hermes_path_prepend 2>/dev/null || true
