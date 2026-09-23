#!/usr/bin/env bash
# Isolated podman run of Cos/herm-tui alias seats. Does not attach live Cos.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_DIR="$(cd "$DIR/../.." && pwd)"
[ -d "$HERMES_DIR" ] || { echo "ERROR: hermes dir missing: $HERMES_DIR" >&2; exit 2; }
ENGINE="${ALIAS_ISOLATION_ENGINE:-}"
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then
    ENGINE=podman
  else
    echo "ERROR: podman is required for alias-isolation sandbox tests" >&2
    exit 2
  fi
fi

IMAGE="${ALIAS_ISOLATION_IMAGE:-localhost/hermes-alias-isolation:test}"
# Bake scripts into the image. Podman machine cannot always bind-mount
# ~/src, and a mount would also risk seeing the live Cos home.
"$ENGINE" build -t "$IMAGE" -f "$DIR/Containerfile" "$HERMES_DIR"

cid="$("$ENGINE" run -d --rm \
  --name "alias-isolation-$$" \
  -e HOME=/tmp/alias-home \
  -e XDG_DATA_HOME=/tmp/alias-home/.local/share \
  -e HERMES_DIR=/src/bin/hermes \
  "$IMAGE" sleep 300)"
cleanup() { "$ENGINE" rm -f "$cid" >/dev/null 2>&1 || true; }
trap cleanup EXIT

"$ENGINE" exec "$cid" bash /src/bin/hermes/tests/alias-isolation/inside.sh
echo "alias-isolation podman checks passed"
