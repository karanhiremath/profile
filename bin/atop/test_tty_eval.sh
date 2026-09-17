#!/usr/bin/env bash
# Wrapper + PTY smoke. Does not attach Cos panes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PATH="$ROOT/bin:$PATH"
ATOP="$ROOT/bin/a-top"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

"$ATOP" vi list >/dev/null || fail "vi list"
"$ATOP" tty --probe | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["schema"]=="atop.tty-eval.probe.v1"' || fail "probe schema"

out="$("$ATOP" tty --settle-ms 400 -- python3 -c 'import os; print("TTY", os.isatty(0), flush=True)')"
printf '%s\n' "$out" | rg -q 'TTY True' || fail "pty isatty: $out"

echo OK
