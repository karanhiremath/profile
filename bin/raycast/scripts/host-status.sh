#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Host Status
# @raycast.mode inline
# @raycast.packageName tmux

# Optional parameters:
# @raycast.icon 📡
# @raycast.refreshTime 5m

PROFILE_DIR="${HOME}/src/profile"
REGISTRY="${PROFILE_DIR}/bin/tmux/hosts/registry.conf"

output=""
while IFS='|' read -r name ssh session desc; do
    [[ -z "$name" || "$name" == \#* ]] && continue

    if [[ "$ssh" == "local" ]]; then
        count=$(tmux list-sessions 2>/dev/null | wc -l | tr -d ' ')
        output+="✅ ${name} (${count} sessions)  "
    else
        if ssh -o ConnectTimeout=1 -o BatchMode=yes "$ssh" "true" 2>/dev/null; then
            output+="✅ ${name}  "
        else
            output+="⬚ ${name}  "
        fi
    fi
done < "$REGISTRY"

echo "$output"
