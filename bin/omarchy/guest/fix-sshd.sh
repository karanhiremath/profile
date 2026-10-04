#!/bin/bash
# Run inside the Omarchy guest (shared as ~/src/.omarchy-host/fix-sshd.sh).
# Starts sshd and installs host public keys. No private keys.
set -euo pipefail

candidates=(
    "${HOME}/src/.omarchy-host/authorized_keys"
    "/mnt/mac/.omarchy-host/authorized_keys"
)
src=""
for path in "${candidates[@]}"; do
    if [[ -f $path ]]; then
        src=$path
        break
    fi
done

if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now ssh || sudo systemctl enable --now sshd || true
elif command -v service >/dev/null 2>&1; then
    sudo service ssh start || sudo service sshd start || true
fi

if [[ -n $src ]]; then
    bash "$(dirname "$src")/install-authorized-keys.sh"
fi

ss -ltn 2>/dev/null | awk '/:22 / {print}' || netstat -lnt 2>/dev/null | awk '/:22 / {print}' || true
echo "omarchy: sshd repair attempted. From the Mac: ssh try-omarchy  # or oma / oma-default"
