#!/usr/bin/env bash
# Runs inside the isolated podman HOME. Never touches the host Cos seat.
set -euo pipefail

HERMES_DIR="${HERMES_DIR:-/src/bin/hermes}"
cd "$HERMES_DIR"
export HOME="${HOME:-/tmp/alias-home}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export HERMES_AGENTS_DATA_HOME="${HERMES_AGENTS_DATA_HOME:-$XDG_DATA_HOME/hermes-agents}"
export PATH="$HERMES_DIR:$PATH"
mkdir -p "$HOME" "$HERMES_AGENTS_DATA_HOME" "$HOME/.local/bin"

fail() { echo "FAIL: $*" >&2; exit 1; }

python3 test_alias_seat.py || fail "alias_seat unit tests"

cos="$(python3 alias_seat.py resolve cos)"
cosw="$(python3 alias_seat.py resolve cosw)"
printf '%s\n' "$cos" | grep -q '"family": "cos"' || fail "cos family: $cos"
printf '%s\n' "$cos" | grep -q '"session": "cos"' || fail "cos session"
printf '%s\n' "$cosw" | grep -q '"family": "cosw"' || fail "cosw family"
cos_root="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["root"])' <<<"$cos")"
cosw_root="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["root"])' <<<"$cosw")"
[ "$cos_root" != "$cosw_root" ] || fail "cos and cosw must not share a home"
case "$cos_root" in
  *"/.hermes") fail "cos root leaked to ~/.hermes: $cos_root" ;;
esac

python3 alias_seat.py write-seat chief-of-staff cos >/dev/null
[ -f "$cos_root/alias.seat.json" ] || fail "seat file missing"

# Stale lock must not look live.
mkdir -p "$cos_root/profiles/chief-of-staff"
printf '999999\n' > "$cos_root/profiles/chief-of-staff/.herm-tui.lock"
python3 alias_seat.py lock-pid chief-of-staff >/dev/null && fail "dead pid 999999 must not hold the lock"
python3 - <<'PY'
import alias_seat
assert alias_seat.clear_stale_locks("chief-of-staff")
PY

# Live lock + desktop pane must win over a mobile shell window.
python3 alias_seat.py write-seat chief-of-staff cos >/dev/null
python3 - <<'PY'
import alias_seat, os
from unittest import mock
alias_seat.write_lock("chief-of-staff", os.getpid())
panes = [
    {"session": "cos", "window": "m", "index": "0", "pid": "9", "command": "zsh", "target": "cos:m.0"},
    {"session": "cos", "window": "0", "index": "0", "pid": str(os.getpid()), "command": "herm", "target": "cos:0.0"},
]
with mock.patch.object(alias_seat, "list_tmux_panes", return_value=panes):
    with mock.patch.object(alias_seat, "pid_in_tree", side_effect=lambda root, wanted: root == os.getpid()):
        assert alias_seat.attach_target("chief-of-staff", "cos") == "cos:0.0"
PY

# Cross-family seat conflict.
python3 - <<'PY'
import json
from pathlib import Path
import alias_seat
root = alias_seat.isolated_root("chief-of-staff")
root.mkdir(parents=True, exist_ok=True)
(root / alias_seat.SEAT_FILENAME).write_text(json.dumps({"family": "cosw", "pinned": True}))
assert alias_seat.homes_conflict("chief-of-staff")
PY

# Inbox homes never include ~/.hermes even if it exists with factory/project-manager.
mkdir -p "$HOME/.hermes/profiles/factory" "$HOME/.hermes/profiles/project-manager"
printf 'project-manager\n' > "$HOME/.hermes/active_profile"
python3 - <<'PY'
import alias_seat
from pathlib import Path
homes = alias_seat.inbox_homes("chief-of-staff")
assert all(".hermes" not in str(h) or "hermes-agents" in str(h) for h in homes)
assert Path.home() / ".hermes" not in homes
for h in homes:
    alias_seat.assert_not_fallback_home(h)
PY

# Pin env must force isolated runtime, not ~/.hermes.
pin="$(python3 alias_seat.py pin-env cos)"
printf '%s\n' "$pin" | grep -q '^HERMES_ALIAS_PIN=1$' || fail "pin flag: $pin"
printf '%s\n' "$pin" | grep -q 'hermes-agents/chief-of-staff' || fail "pin home: $pin"
printf '%s\n' "$pin" | grep -q "$HOME/.hermes" && fail "pin leaked ~/.hermes: $pin"

# Owned aliases must stay distinct from hermes -p wrappers.
python3 - <<'PY'
from pathlib import Path
text = Path("/src/bin/hermes/cos").read_text(encoding="utf-8")
assert "hermes -p" not in text
assert "chief-of-staff" in text
PY

echo "alias-isolation inside checks passed"
