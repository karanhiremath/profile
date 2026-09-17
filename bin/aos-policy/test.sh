#!/usr/bin/env bash
# aos-policy engine / ACL / facade smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cd "$ROOT/bin/aos-policy"
python3 test_engine.py
python3 test_acl.py

CLI="$ROOT/bin/aos-policy/aos-policy"
chmod 755 "$CLI" "$ROOT/bin/aos" install
export AOS_POLICY="$CLI"
export AOS_POLICY_HOME
AOS_POLICY_HOME="$(mktemp -d "${TMPDIR:-/tmp}/aos-policy-test.XXXXXX")"
cleanup() { rm -rf "$AOS_POLICY_HOME"; }
trap cleanup EXIT

"$CLI" list --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert any(p["id"]=="herm-tui-cursor-exclusive" for p in d["policies"])'
printf '%s\n' '["Task","pi__subagent","Read"]' | "$CLI" eval --surface catalog.tools --wrapper herm-tui --provider cursor | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["items"]==["pi__subagent"]'
printf 'hello tool juggling world\n' | "$CLI" eval --surface stream.outbound --wrapper herm-tui --provider cursor | python3 -c 'import sys; t=sys.stdin.read().lower(); assert "tool juggling" not in t; assert "hello" in t'
"$ROOT/bin/aos" policy status --wrapper herm-tui --provider cursor | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["active"]>=1'

printf 'aos-policy tests ok\n'
