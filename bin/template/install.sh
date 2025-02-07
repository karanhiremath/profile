#!/bin/bash

set -euo pipefail

shopt -s failglob

. "${PROFILE_DIR}"/bin/sh/shell_fns --source-only

app_name="APP NAME"

MACHINE="$(uname -s)"
ARCH="$(uname -m)"

if cmd_test_or_install $app_name -eq 0; then
    echo "Already installed!"
else
    install_messages "start" "$app_name"

    case "${MACHINE}" in
        Linux)  echo "Linux specific install instructions here";;
        Darwin)    echo "Mac install instructions here";;
        *)      echo "Generic install instructions here";;
    esac

    case "${ARCH}" in
        aarch64)  echo "aarch64 architecture specific install instructions here";;
        *)      echo "Generic install instructions here";;
    esac

    install_messages "end" "$app_name"
fi
