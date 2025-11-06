#!/bin/bash

set -euo pipefail

shopt -s failglob

. "${PROFILE_DIR}"/bin/sh/shell_fns --source-only

app_name="alfred"

MACHINE="$(uname -s)"
ARCH="$(uname -m)"

install_messages "start" "$app_name"

case "${MACHINE}" in
    Darwin|Mac)
        echo "Installing Alfred on Mac..."
        # Alfred is Mac-only
        brew install --cask alfred
        ;;
    Linux)
        echo "Alfred is only available for macOS."
        echo "For Linux alternatives, consider: ulauncher, albert, or rofi"
        exit 1
        ;;
    *)
        echo "Alfred is only available for macOS."
        exit 1
        ;;
esac

install_messages "end" "$app_name"
