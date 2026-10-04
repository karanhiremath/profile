#!/bin/bash
# Post-reset guest bind. Run once after every Omarchy factory reset.
# Installs host public keys and starts sshd. No private keys.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ -x ${HERE}/fix-sshd.sh ]]; then
    bash "${HERE}/fix-sshd.sh"
else
    echo "omarchy: missing ${HERE}/fix-sshd.sh" >&2
    exit 1
fi

cat <<'EOF'
omarchy: guest bind done.

From the Mac (prefer MagicDNS after this guest joins the tailnet):
  ssh try-omarchy.tail1e8436.ts.net
  ssh try-omarchy          # QEMU fallback 127.0.0.1:2222
  oma / oma-default        # VM instance tmux (session home)
  oma-s                    # podman tmux inside this VM

Join the tailnet on this guest. Host bind is hostctl omarchy bind; do not use this script as the SOP.
EOF
