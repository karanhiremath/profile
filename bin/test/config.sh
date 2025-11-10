#!/bin/bash
# Common configuration for testing

# Detect container engine (prefer podman over docker)
detect_container_engine() {
    if command -v podman >/dev/null 2>&1; then
        echo "podman"
    elif command -v docker >/dev/null 2>&1; then
        echo "docker"
    else
        echo ""
    fi
}

# Set container engine
export CONTAINER_ENGINE="${CONTAINER_ENGINE:-$(detect_container_engine)}"

# Fix D-Bus session address for podman if needed
# This prevents "Interactive authentication required" errors in CI environments
# Only applies to Linux systems where /run directory exists
if [ "$CONTAINER_ENGINE" = "podman" ]; then
    # Ensure XDG_RUNTIME_DIR is set (Linux only)
    if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
        runtime_dir="/run/user/$(id -u)"
        if [ -d "$runtime_dir" ]; then
            export XDG_RUNTIME_DIR="$runtime_dir"
        fi
    fi
    
    # Fix DBUS_SESSION_BUS_ADDRESS if it's pointing to wrong user (Linux only)
    if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ]; then
        expected_bus="unix:path=${XDG_RUNTIME_DIR}/bus"
        if [ "$DBUS_SESSION_BUS_ADDRESS" != "$expected_bus" ] && [ -S "${XDG_RUNTIME_DIR}/bus" ]; then
            export DBUS_SESSION_BUS_ADDRESS="$expected_bus"
        fi
    fi
fi

# Test configuration variables
export TEST_TIMEOUT="${TEST_TIMEOUT:-600}"
export TEST_VERBOSE="${TEST_VERBOSE:-0}"
export TEST_KEEP_CONTAINERS="${TEST_KEEP_CONTAINERS:-0}"

# Container image names
export UBUNTU_IMAGE="${UBUNTU_IMAGE:-ubuntu:latest}"
export RHEL8_IMAGE="${RHEL8_IMAGE:-redhat/ubi8:latest}"
export NIXOS_IMAGE="${NIXOS_IMAGE:-nixos/nix:latest}"

# Apps to test
export APPS_TO_TEST="${APPS_TO_TEST:-git tmux vim zsh bash}"

# Test result colors
export COLOR_GREEN='\033[0;32m'
export COLOR_RED='\033[0;31m'
export COLOR_YELLOW='\033[1;33m'
export COLOR_RESET='\033[0m'

# Helper functions
log_info() {
    echo -e "${COLOR_GREEN}[INFO]${COLOR_RESET} $*"
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $*"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"
}
