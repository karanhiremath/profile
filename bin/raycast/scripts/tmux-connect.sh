#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Connect to Host
# @raycast.mode silent
# @raycast.packageName tmux

# Optional parameters:
# @raycast.icon 🖥
# @raycast.argument1 { "type": "dropdown", "placeholder": "Host", "data": [{"title": "Local", "value": "local"}, {"title": "Together AI", "value": "togetherai"}, {"title": "Mac Mini", "value": "mini"}, {"title": "Training", "value": "training"}, {"title": "TGK2 C1", "value": "tgk2-c1"}, {"title": "TGK2 C2", "value": "tgk2-c2"}, {"title": "CXIS Login", "value": "cxis-login"}, {"title": "CXIS Dev", "value": "cxis-dev"}] }

HOST="$1"
PROFILE_DIR="${HOME}/src/profile"

# Open Ghostty with tmux-connect
open -na "Ghostty.app" --args -e "${PROFILE_DIR}/bin/tmux/tmux-connect" "${HOST}"

echo "Connecting to ${HOST}..."
