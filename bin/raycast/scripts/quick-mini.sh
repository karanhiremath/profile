#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Quick Connect — Mac Mini
# @raycast.mode silent
# @raycast.packageName tmux

# Optional parameters:
# @raycast.icon 🏠

PROFILE_DIR="${HOME}/src/profile"
open -na "Ghostty.app" --args -e "${PROFILE_DIR}/bin/tmux/tmux-connect" "mini"
echo "Connecting to Mac Mini..."
