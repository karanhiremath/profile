#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
test_root="$(mktemp -d /private/tmp/tmux-agent-test.XXXXXX)"
trap 'rm -rf "$test_root"' EXIT
mkdir -p "$test_root/bin" "$test_root/policies"
cat > "$test_root/hosts" <<'EOF'
fixture-host|fixture-host|home|fixture
EOF
cat > "$test_root/bin/cauth-fixture" <<'EOF'
#!/bin/bash
set -euo pipefail
python3 - "$@" <<'PY'
import json,os,sys
with open(os.environ['CAUTH_FIXTURE_RECEIPT'],'w') as out:json.dump(sys.argv[1:],out)
print('fixture-session: 1 windows')
PY
EOF
chmod 700 "$test_root/bin/cauth-fixture"
export CAUTH_SSH_AGENT_BIN="$test_root/bin/cauth-fixture" CAUTH_SSH_POLICY_DIR="$test_root/policies"
export CAUTH_FIXTURE_RECEIPT="$test_root/receipt" TMUX_CONNECT_EXTRA_REGISTRIES="$test_root/hosts"
export XDG_CACHE_HOME="$test_root/cache"
"$root/tmux-connect" fixture-host --agent --ls > "$test_root/output"
python3 - "$test_root/receipt" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x[0]=='exec';assert x[x.index('--host')+1]=='fixture-host';assert '--batch' in x;assert x[-1]=='tmux list-sessions'
PY
"$root/tmux-connect" --sandbox fixture-host fixture-box --agent --ls > "$test_root/output"
python3 - "$test_root/receipt" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x[-1]=='podman exec fixture-box tmux list-sessions';assert '--host' in x
PY
