#!/usr/bin/env bash
# Dry-run + help. No Ghostty, no tmux attach, no Linear API.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/open-issue"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

chmod +x "$BIN"
"$BIN" --help | grep -q 'LINEAR_WORK_DIR' || fail "help"
"$BIN" --print-prompt-template | grep -q '{{issue.identifier}}' || fail "template vars"
"$BIN" --print-prompt-template | grep -q '{{issue.branchName}}' || fail "branch var"
if "$BIN" --print-prompt-template | grep -q '^---'; then
  fail "frontmatter leaked"
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/linear-open-issue.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
export XDG_CACHE_HOME="$tmp/cache"
export PC_SRC_DIR="$tmp/src"
export HOME="$tmp/home"
mkdir -p "$PC_SRC_DIR/bifrost" "$PC_SRC_DIR/linear-open-issue-fixture" "$HOME"

export LINEAR_ISSUE_IDENTIFIER="KH-123"
export LINEAR_ISSUE_BRANCH_NAME="kh-123-linear-open-issue"
export LINEAR_WORK_DIR="$PC_SRC_DIR/linear-open-issue-fixture"
export LINEAR_PROJECT_NAME="cdev"
export LINEAR_PROMPT="Implement KH-123 in the selected repo."

out="$("$BIN" --dry-run)"
printf '%s\n' "$out" | python3 -c '
import json, os, sys
d = json.load(sys.stdin)
assert d["schema"] == "linear-open-issue.v1", d
assert d["issue"] == "KH-123", d
assert d["project"] == "linear-open-issue-fixture", d
assert d["branch"] == "kh-123-linear-open-issue", d
assert d["action"] == "create", d
assert d["workdir"].endswith("linear-open-issue-fixture"), d
assert os.path.isfile(d["prompt_file"]), d
body = open(d["prompt_file"], encoding="utf-8").read()
assert "Implement KH-123" in body, body
assert "pc_project: linear-open-issue-fixture" in body, body
'

# nested path still maps to the longest src project
export LINEAR_WORK_DIR="$PC_SRC_DIR/linear-open-issue-fixture/apps"
mkdir -p "$LINEAR_WORK_DIR"
out="$("$BIN" --dry-run)"
printf '%s\n' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d["project"] == "linear-open-issue-fixture", d
'

# missing workdir
if LINEAR_WORK_DIR="" "$BIN" --dry-run >/dev/null 2>"$tmp/err"; then
  fail "empty workdir should fail"
fi
grep -q 'LINEAR_WORK_DIR' "$tmp/err" || fail "empty workdir message"

# workdir outside src
if LINEAR_WORK_DIR="$tmp" "$BIN" --dry-run >/dev/null 2>"$tmp/err2"; then
  fail "outside src should fail"
fi
grep -q 'not under' "$tmp/err2" || fail "outside src message"

# install writes coding-tools.json with an absolute path
export HOME="$tmp/home"
export LINEAR_OPEN_ISSUE_SKIP_PBCOPY=1
"$DIR/install" >/dev/null
python3 - "$HOME/.linear/coding-tools.json" "$BIN" <<'PY'
import json, os, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
path = cfg["openIssue"]["path"]
assert os.path.isabs(path), path
assert os.path.samefile(path, sys.argv[2]), (path, sys.argv[2])
assert "LINEAR_PROMPT" in cfg["openIssue"]["env"]
PY
[ -L "$HOME/.pi/agent/prompts/linear-issue.md" ] || fail "pi prompt link"

echo OK
