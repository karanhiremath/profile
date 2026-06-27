#!/usr/bin/env bash
#
# validate.sh — smoke-test a built agent-desktop image in the local podman VM.
# Iteration 1: confirm the image runs and reports its variant.
# Later iterations: also probe noVNC port, browser, and seeded agent CLIs.

set -euo pipefail

IMG="${1:-localhost/agent-desktop-min:dev}"

usage() {
    cat <<EOF
validate.sh — smoke-test an agent-desktop image.

USAGE
    validate.sh [IMAGE]   (default: localhost/agent-desktop-min:dev)
EOF
}
case "${1:-}" in -h|--help) usage; exit 0 ;; esac

echo "=== run smoke test: ${IMG} ==="
podman run --rm "${IMG}" bash -c '
    echo "variant: ${AGENT_DESKTOP_VARIANT:-unset}"
    echo "bash:    $(bash --version | head -1)"
    echo "coreutils present: $(command -v ls >/dev/null && echo yes || echo no)"
'
echo "=== OK ==="
