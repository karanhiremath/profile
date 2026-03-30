#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Quick Connect — Together AI
# @raycast.mode silent
# @raycast.packageName tmux

# Optional parameters:
# @raycast.icon 🚀

PROFILE_DIR="${HOME}/src/profile"
open -na "Ghostty.app" --args -e "${PROFILE_DIR}/bin/tmux/tmux-connect" "togetherai"
echo "Connecting to Together AI..."
