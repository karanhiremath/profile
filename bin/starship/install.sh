#!/bin/bash

set -euo pipefail

shopt -s failglob

. $PROFILE_DIR/bin/sh/shell_fns --source-only

app_name="starship"

install_messages "start" "$app_name"

curl -sS https://starship.rs/install.sh | sh

ln -fs ./starship.toml ~/.config/starship.toml

install_messages "end" "$app_name"
