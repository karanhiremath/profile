#!/usr/bin/env bash
#
# build-in-container.sh — build an agent-desktop image via nix, WITHOUT installing
# nix on the host. Runs the build inside a disposable nixos/nix container, then
# loads the resulting OCI image into podman.
#
# This keeps the host pristine: the only host dependency is podman.

set -euo pipefail

TARGET="${1:-desktop-min}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAKE_DIR="$(cd "${SCRIPT_DIR}/../nix" && pwd)"
NIX_IMG="${NIX_IMG:-docker.io/nixos/nix:latest}"

usage() {
    cat <<EOF
build-in-container.sh — nix-build an agent-desktop image in a disposable container.

USAGE
    build-in-container.sh [TARGET]

ARGS
    TARGET   flake package to build (default: desktop-min)

ENV
    NIX_IMG  nix builder image (default: docker.io/nixos/nix:latest)

The host needs only podman; nix runs inside the builder container.
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

echo "=== building flake target '#${TARGET}' inside ${NIX_IMG} ==="
podman run --rm \
    -v "${FLAKE_DIR}":/flake:ro \
    -v "${OUT}":/out \
    "${NIX_IMG}" \
    bash -euo pipefail -c "
        # Copy flake to a writable dir so nix can write flake.lock without
        # touching the read-only host source.
        cp -r /flake /build
        nix --extra-experimental-features 'nix-command flakes' \
            build '/build#${TARGET}' --out-link /out/result --print-build-logs
        cp -L /out/result /out/image.tar.gz
    "

echo "=== loading image into podman ==="
podman load -i "${OUT}/image.tar.gz"

echo "=== done. inspect with: podman images | grep agent-desktop ==="
