#!/usr/bin/env bash
# Converge the hermes fleet to the crusoe-hermes-homes contract:
#   1. stop + disable every hermes-gateway-<profile> unit on every host
#   2. patch every host's code planes (HERMES_STATE_JOURNAL_MODE honored —
#      profile/bin/hermes/patch-nfs-journal-env.py: venv + worktree overlays)
#   3. offline-convert WAL stores to journal_mode=delete (python over ssh stdin)
#   4. enable + start the contract-wrap gateway unit on exactly ONE owner host
#
# Run from a host WITH ssh egress to the fleet (workstation / Mac / tc host
# with the cluster agent key). Default dry-run; --apply mutates.
#
# stdout: machine JSON only (fleet-converge.v1). stderr: diagnostics.
# Hosts: HERMES_FLEET_HOSTS (default INCLUDES cxis-login-0 — tc-healthcheck's
# default list omits login hosts and their gateways go unmanaged; observed
# 2026-09-29). Owner: HERMES_GATEWAY_OWNER.
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

HOSTS="${HERMES_FLEET_HOSTS:-cxis-devlarge-0 cxis-devlarge-1 cxis-devlarge-2 cxis-login-0}"
OWNER="${HERMES_GATEWAY_OWNER:-cxis-devlarge-2}"
PROFILES="${HERMES_FLEET_PROFILES:-chief-of-staff-work chief-of-staff}"
PY_LOCAL="$HOME/.local/share/hermes-toolchain/venv/bin/python"
PY_REMOTE="\$HOME/.local/share/hermes-toolchain/venv/bin/python"
PATCHER_FILE="$HOME/src/profile/bin/hermes/patch-nfs-journal-env.py"

conv_py() { # $1 = profile
  cat <<PYEOF
import sqlite3, pathlib, os
profile = "$1"
root = os.environ.get("HERMES_AGENTS_DATA_HOME", "/shared/people/" + os.environ.get("USER", "") + "/hermes-agents")
nested = pathlib.Path(root) / profile / "profiles" / profile
home = nested if nested.is_dir() else pathlib.Path(root) / profile
db = home / "state.db"
if db.exists():
    try:
        c = sqlite3.connect(str(db), timeout=30)
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        if mode == "wal":
            mode = c.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            c.execute("PRAGMA synchronous=FULL")
        c.close()
        print(profile + ": " + str(mode))
    except Exception as e:
        print(profile + ": ERROR " + str(e))
else:
    print(profile + ": no-db")
PYEOF
}

report="$("$PY_LOCAL" - "$PATCHER_FILE" "$HOSTS" "$OWNER" "$PROFILES" "$APPLY" <<'PYEOF'
import json, subprocess, sys
from pathlib import Path

patcher_path = sys.argv[1]
hosts, owner, profiles, apply = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] == "1"
rows = []
ok = True

def ssh(host, script, stdin_text=None, timeout=60):
    try:
        p = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
                            host, script],
                           input=stdin_text, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return 127, "", str(e)[:200]

for h in hosts.split():
    if not apply:
        rows.append({"host": h, "owner": h == owner, "dry_run": True, "steps": []})
        continue
    steps = []
    # 1. stop + disable gateway units
    for prof in profiles.split():
        rc, out, err = ssh(h, f"systemctl --user stop hermes-gateway-{prof}.service; "
                              f"systemctl --user disable hermes-gateway-{prof}.service; true")
        steps.append({"step": "stop-unit", "profile": prof, "rc": rc})
    # 2. patch journal-mode env on all code planes — pipe the patcher over
    #    ssh stdin so remote hosts don't need the profile repo synced
    rc, out, err = ssh(h, "$HOME/.local/share/hermes-toolchain/venv/bin/python - || python3 -",
                       stdin_text=Path(patcher_path).read_text())
    steps.append({"step": "patch-journal-env", "rc": rc,
                  "ok": '"ok": true' in out})
    ok = ok and ('"ok": true' in out)
    # 3. offline WAL -> delete conversion (python over ssh stdin)
    for prof in profiles.split():
        conv = f"""import sqlite3, pathlib, os
profile = {prof!r}
root = os.environ.get("HERMES_AGENTS_DATA_HOME", "/shared/people/" + os.environ.get("USER", "") + "/hermes-agents")
nested = pathlib.Path(root) / profile / "profiles" / profile
home = nested if nested.is_dir() else pathlib.Path(root) / profile
db = home / "state.db"
if db.exists():
    try:
        c = sqlite3.connect(str(db), timeout=30)
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        if mode == "wal":
            mode = c.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            c.execute("PRAGMA synchronous=FULL")
        c.close()
        print(profile + ": " + str(mode))
    except Exception as e:
        print(profile + ": ERROR " + str(e))
else:
    print(profile + ": no-db")
"""
        rc, out, err = ssh(h, "$HOME/.local/share/hermes-toolchain/venv/bin/python -", conv)
        steps.append({"step": "convert-wal", "profile": prof, "rc": rc,
                      "out": out.splitlines()[0] if out else err[:120]})
    # 4. owner: enable + start contract units
    if h == owner:
        for prof in profiles.split():
            rc, out, err = ssh(h, f"systemctl --user enable hermes-gateway-{prof}.service && "
                                  f"systemctl --user start hermes-gateway-{prof}.service && "
                                  f"sleep 3 && systemctl --user is-active hermes-gateway-{prof}.service",
                               timeout=90)
            state = out.splitlines()[-1] if out else err[:120]
            good = state == "active"
            steps.append({"step": "start-owner-unit", "profile": prof,
                          "state": state, "ok": good})
            ok = ok and good
    rows.append({"host": h, "owner": h == owner, "steps": steps})

print(json.dumps({"schema_version": "fleet-converge.v1", "apply": apply,
                  "owner": owner, "hosts": rows, "ok": ok}))
PYEOF
)"

printf '%s\n' "$report"
[ "$APPLY" = 1 ] || echo "DRY-RUN: re-run with --apply to converge. Requires ssh egress + cluster agent key." >&2