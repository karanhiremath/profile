#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: macos-ghostty-alert.sh --title TITLE --message MESSAGE --details-file PATH [--ghostty] [--ghostty-tty TTY] [--notification-only]

Generic local notification helper. Keep project-specific data in caller-provided title/message/details only.
USAGE
}

TITLE="Pi alert"
MESSAGE="Status changed"
DETAILS_FILE=""
OPEN_GHOSTTY=false
GHOSTTY_TTY=""
NOTIFICATION_ONLY=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --title) TITLE="$2"; shift 2 ;;
    --message) MESSAGE="$2"; shift 2 ;;
    --details-file) DETAILS_FILE="$2"; shift 2 ;;
    --ghostty) OPEN_GHOSTTY=true; shift ;;
    --ghostty-tty) GHOSTTY_TTY="$2"; shift 2 ;;
    --notification-only) NOTIFICATION_ONLY=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$DETAILS_FILE" ] || [ ! -f "$DETAILS_FILE" ]; then
  echo "--details-file must point to an existing file" >&2
  exit 2
fi

json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }
TITLE_JSON="$(printf '%s' "$TITLE" | json_escape)"
MESSAGE_JSON="$(printf '%s' "$MESSAGE" | json_escape)"
DIALOG_JSON="$(printf '%s\n\nDetails: %s' "$MESSAGE" "$DETAILS_FILE" | json_escape)"

# Known-good macOS notification path. This appears under Script Editor/osascript.
/usr/bin/osascript >/dev/null 2>&1 <<OSA || true
display notification $MESSAGE_JSON with title $TITLE_JSON sound name "Glass"
OSA

if [ "$NOTIFICATION_ONLY" != true ]; then
  (
    /usr/bin/osascript >/dev/null 2>&1 <<OSA || true
with timeout of 20 seconds
  display dialog $DIALOG_JSON with title $TITLE_JSON buttons {"OK"} default button "OK" giving up after 15
end timeout
OSA
  ) &
fi

# Ghostty-native path: emit terminal notification OSCs into a Ghostty/tmux pane TTY.
# If the caller is inside tmux, the TTY should be `tmux display -p '#{pane_tty}'` and
# `allow-passthrough` should be on for that pane/session.
if [ "$NOTIFICATION_ONLY" != true ] && [ -n "$GHOSTTY_TTY" ] && [ -w "$GHOSTTY_TTY" ]; then
  {
    printf '\033Ptmux;\033\033]777;notify;%s;%s\007\033\\' "$TITLE" "$MESSAGE"
    printf '\033Ptmux;\033\033]9;%s: %s\007\033\\' "$TITLE" "$MESSAGE"
    printf '\033]777;notify;%s;%s\007' "$TITLE" "$MESSAGE"
    printf '\033]9;%s: %s\007' "$TITLE" "$MESSAGE"
  } > "$GHOSTTY_TTY" 2>/dev/null || true
fi

# Best-effort Ghostty window. On macOS Ghostty CLI +new-window is unsupported; open -a
# may not deep-link into an existing pane, so this is supplemental only.
if [ "$NOTIFICATION_ONLY" != true ] && [ "$OPEN_GHOSTTY" = true ]; then
  RUNNER="${TMPDIR:-/tmp}/pi-alert-ghostty-runner.sh"
  cat > "$RUNNER" <<'EOF_RUNNER'
#!/usr/bin/env bash
set -euo pipefail
printf '\033]0;Pi alert\007'
printf '\n=== Pi alert ===\n\n'
cat "$1"
printf '\n\nPress Enter to close this window.\n'
read -r _ || true
EOF_RUNNER
  chmod +x "$RUNNER"
  /usr/bin/osascript -e 'tell application "Ghostty" to activate' >/dev/null 2>&1 || true
  open -a Ghostty --args -e "$RUNNER" "$DETAILS_FILE" >/dev/null 2>&1 || true
fi
