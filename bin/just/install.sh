#!/bin/bash

set -euo pipefail

shopt -s failglob

. $PROFILE_DIR/bin/sh/shell_fns --source-only

app_name="just"

MACHINE="$(uname -s)"
ARCH="$(uname -m)"

install_messages "start" "$app_name"

if [[ $(cargo install just) -ne 0 ]]; then
    case "${MACHINE}" in
        Linux)  echo "Linux specific install instructions here";;
        Mac)    brew install just;;
        *)      echo "Generic install instructions here";;
    esac

    case "${ARCH}" in
        aarch64)  echo "aarch64 architecture specific install instructions here";;
        *)      echo "Generic install instructions here";;
    esac
fi

install_messages "end" "$app_name"

