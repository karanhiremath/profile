#!/bin/bash
# Common configuration for testing

# Test configuration variables
export TEST_TIMEOUT="${TEST_TIMEOUT:-600}"
export TEST_VERBOSE="${TEST_VERBOSE:-0}"
export TEST_KEEP_CONTAINERS="${TEST_KEEP_CONTAINERS:-0}"

# Docker image names
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
