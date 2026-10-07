#!/usr/bin/env bash
# Regression: failed transport/commands cannot erase cached inventory.
set -euo pipefail
if [[ "${1:-}" == --help ]]; then
  echo 'Usage: test-probe-failures.sh' >&2
  exit 0
fi
root="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/cache/tmux-connect/sessions" "$tmp/cache/tmux-connect/sandboxes"
cat >"$tmp/bin/ssh" <<'SH'
#!/usr/bin/env bash
[[ "${FAKE_STATUS:-0}" == 0 ]] || exit "$FAKE_STATUS"
[[ "${FAKE_EMPTY:-0}" == 1 ]] || echo 'live: 1 windows'
SH
chmod +x "$tmp/bin/ssh"
echo 'probe|probe-host|home|fixture' >"$tmp/registry"
export PATH="$tmp/bin:$PATH" XDG_CACHE_HOME="$tmp/cache" TMUX_CONNECT_EXTRA_REGISTRIES="$tmp/registry"
for code in 1 2 126 255; do
  export FAKE_STATUS="$code"
  for mode in sessions sandboxes sandbox-sessions; do
    case "$mode" in
      sessions) args=(--ls probe); cache="$tmp/cache/tmux-connect/sessions/probe" ;;
      sandboxes) args=(--sandbox --ls probe); cache="$tmp/cache/tmux-connect/sandboxes/probe" ;;
      sandbox-sessions) args=(--sandbox probe box --ls); cache="$tmp/cache/tmux-connect/sessions/probe--box" ;;
    esac
    echo retained >"$cache"
    if "$root/tmux-connect" "${args[@]}" >"$tmp/out" 2>"$tmp/err"; then
      echo "FAIL: $mode status $code became success" >&2; exit 1
    fi
    grep -qx retained "$cache"
    test ! -s "$tmp/out"
    grep -q 'probe failed' "$tmp/err"
  done
done
export FAKE_STATUS=0 FAKE_EMPTY=1
"$root/tmux-connect" --sandbox --ls probe >"$tmp/out" 2>"$tmp/err"
test ! -s "$tmp/cache/tmux-connect/sandboxes/probe"
test ! -s "$tmp/out"
export FAKE_EMPTY=0
"$root/tmux-connect" --ls probe >"$tmp/out"
grep -qx live "$tmp/cache/tmux-connect/sessions/probe"
