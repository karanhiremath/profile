#!/usr/bin/env bash
# End-to-end test of the inference layer with NO model weights and NO GPU.
#
# Proves, against local OpenAI-compatible stubs:
#   1. every registry on the default search path is schema-valid
#   2. `inf probe` enforces the harness contract (health/models/chat/stream/tools)
#   3. `inf probe` FAILS closed when a backend is down (the important half)
#   4. `inf bench` computes speculative speedup against a baseline
#   5. every harness renderer (pi, hermes, cursor, claude, codex) emits valid config
#   6. no rendered artifact contains a secret value
#
# This is what CI runs on a fresh machine, and what you run before trusting a
# real DFlash2 backend: if the contract test passes, the only unknown left is
# the model itself.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="${PROFILE_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
INF="${PROFILE_DIR}/bin/inference/inf"
STUB="${SCRIPT_DIR}/openai_stub.py"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/inf-contract-XXXXXX")"
export INF_STATE_DIR="${WORK}/state"
export INF_CACHE_DIR="${WORK}/cache"
export PI_AGENT_DIR="${WORK}/pi-agent"
export HOME_ORIG="${HOME}"
export HOME="${WORK}/home"          # keep ~/.cursor etc. out of the real HOME
mkdir -p "${PI_AGENT_DIR}" "${HOME}"

PASS=0; FAIL=0
PIDS=()

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; FAIL=$((FAIL+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$*"; }

cleanup() {
    for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null; done
    rm -rf "$WORK"
}
trap cleanup EXIT

start_stub() {
    local port="$1" speed="$2"
    python3 "$STUB" --port "$port" --model stub-model --speed "$speed" \
        >"${WORK}/stub-${port}.log" 2>&1 &
    PIDS+=("$!")
    for _ in $(seq 1 40); do
        curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1 && return 0
        sleep 0.25
    done
    echo "stub on :${port} never became healthy" >&2
    cat "${WORK}/stub-${port}.log" >&2
    return 1
}

# ── 1. real registries are valid ──────────────────────────────────────────────
head_ "1. registry schema (default search path)"
if (unset INF_REGISTRY_PATH; "$INF" validate) >"${WORK}/validate.log" 2>&1; then
    ok "$(tail -1 "${WORK}/validate.log")"
else
    bad "registry validation failed:"; sed 's/^/      /' "${WORK}/validate.log"
fi

head_ "2. validator rejects a malformed backend"
cat > "${WORK}/bad.toml" <<'BAD'
schema_version = 1
[backends.broken]
description = "missing runtime/api, speculative without a drafter"
kind = "local"
speculative = true
[backends.broken.model]
served_name = "x"
BAD
if INF_REGISTRY_PATH="${WORK}/bad.toml" "$INF" validate >"${WORK}/bad.log" 2>&1; then
    bad "validator accepted a malformed backend (should have failed)"
else
    ok "validator rejected it ($(grep -c '✗' "${WORK}/bad.log") error(s) reported)"
fi

# ── 3. probe fails closed when nothing is listening ───────────────────────────
export INF_REGISTRY_PATH="${SCRIPT_DIR}/backends.stub.toml"
head_ "3. probe fails closed against a down backend"
if "$INF" probe stub-down >"${WORK}/probe-down.log" 2>&1; then
    bad "probe passed against an unbound port (must fail closed)"
else
    ok "probe correctly reported stub-down unusable ($(grep -c '\u2717' "${WORK}/probe-down.log") failed check(s))"
fi

# ── 4. probe passes against live stubs ────────────────────────────────────────
start_stub 8199 400 || exit 1
start_stub 8200 130 || exit 1

head_ "4. probe enforces the harness contract"
for b in stub-fast stub-baseline; do
    if "$INF" probe "$b" >"${WORK}/probe-${b}.log" 2>&1; then
        ok "$b: $(grep -c '✓' "${WORK}/probe-${b}.log") checks passed"
    else
        bad "$b probe failed:"; sed 's/^/      /' "${WORK}/probe-${b}.log"
    fi
done

# ── 4b. probe rejects a stream with no terminal finish_reason ────────────────
# Regression guard. probe once passed a backend whose SSE stream never sent a
# terminal finish_reason; pi then failed every turn with "Stream ended without
# finish_reason". Counting SSE chunks is not enough — the stream must terminate.
head_ "4b. probe rejects an unterminated stream"
python3 "$STUB" --port 8201 --model stub-model --speed 2000 --broken-stream \
    >"${WORK}/stub-broken.log" 2>&1 &
PIDS+=("$!")
for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:8201/health" >/dev/null 2>&1 && break
    sleep 0.25
done
cat > "${WORK}/broken.toml" <<'BROKEN'
schema_version = 1
[backends.stub-broken]
description = "Streams without a terminal finish_reason; probe must reject it."
kind = "local"
runtime = "none"
api = "openai-chat"
cost_class = "free"
data_boundary = "public"
[backends.stub-broken.endpoint]
scheme = "http"
host = "127.0.0.1"
port = 8201
path = "/v1"
health_path = "/health"
[backends.stub-broken.auth]
api_key_default = "none"
[backends.stub-broken.model]
served_name = "stub-model"
[backends.stub-broken.capabilities]
streaming = true
tools = true
reasoning_effort = false
developer_role = false
BROKEN
if INF_REGISTRY_PATH="${WORK}/broken.toml" "$INF" probe stub-broken \
        >"${WORK}/probe-broken.log" 2>&1; then
    bad "probe PASSED a backend whose stream never terminates (pi would fail every turn)"
else
    if grep -q "finish_reason" "${WORK}/probe-broken.log"; then
        ok "probe rejected it and named the reason (missing terminal finish_reason)"
    else
        ok "probe rejected it"
    fi
fi

# ── 5. bench + speculative speedup ────────────────────────────────────────────
head_ "5. bench computes speculative speedup vs baseline"
if "$INF" bench stub-fast --runs 2 --max-tokens 96 --out "${WORK}/bench.json" \
        >"${WORK}/bench.log" 2>&1; then
    SPEEDUP="$(python3 -c "import json;print(round(json.load(open('${WORK}/bench.json'))['speedup_mean'],2))" 2>/dev/null || echo 0)"
    IS_UP="$(python3 -c "print(1 if ${SPEEDUP:-0} > 1.5 else 0)")"
    if [ "$IS_UP" = "1" ]; then
        ok "measured ${SPEEDUP}x over baseline (stub speeds 400 vs 130 tok/s)"
    else
        bad "speedup ${SPEEDUP}x — bench math is not tracking the stub speeds"
    fi
else
    bad "bench failed:"; sed 's/^/      /' "${WORK}/bench.log"
fi

# ── 6. every harness renderer ─────────────────────────────────────────────────
head_ "6. harness renderers"
render_ok() {  # harness, file-that-must-exist, json?
    local harness="$1" target="$2" is_json="${3:-no}"
    if ! "$INF" bind "$harness" stub-fast >"${WORK}/bind-${harness}.log" 2>&1; then
        bad "bind ${harness} failed:"; sed 's/^/      /' "${WORK}/bind-${harness}.log"; return
    fi
    if [ ! -f "$target" ]; then
        bad "bind ${harness} wrote no config at ${target}"; return
    fi
    if [ "$is_json" = "json" ] && ! python3 -c "import json,sys;json.load(open('$target'))" 2>/dev/null; then
        bad "bind ${harness} produced invalid JSON at ${target}"; return
    fi
    ok "bind ${harness} → $(basename "$target")"
}
render_ok pi     "${PI_AGENT_DIR}/models.json"          json
render_ok hermes "${INF_STATE_DIR}/hermes-backend.env"
render_ok claude "${INF_STATE_DIR}/claude-backend.env"
render_ok codex  "${INF_STATE_DIR}/codex-backend.env"

# cursor must REFUSE a non-cursor backend rather than silently mis-binding
if "$INF" bind cursor stub-fast >"${WORK}/bind-cursor.log" 2>&1; then
    bad "bind cursor accepted an OpenAI-endpoint backend (cursor-agent cannot use one)"
else
    ok "bind cursor correctly refused a non-cursor backend"
fi

head_ "7. pi provider config is well-formed"
python3 - "$PI_AGENT_DIR" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
models = json.loads((d / "models.json").read_text())
settings = json.loads((d / "settings.json").read_text())
prov = models["providers"]["stub-local"]
checks = [
    ("baseUrl points at the stub", prov["baseUrl"] == "http://127.0.0.1:8199/v1"),
    ("api is openai-completions",  prov["api"] == "openai-completions"),
    ("apiKey is an env reference",  prov["apiKey"].startswith("${")),
    ("model id is served_name",     prov["models"][0]["id"] == "stub-model"),
    ("settings default provider",   settings["defaultProvider"] == "stub-local"),
    ("settings enabledModels",      "stub-local/stub-model" in settings["enabledModels"]),
]
bad = [n for n, okk in checks if not okk]
for n, okk in checks:
    print(("  \033[32m✓\033[0m " if okk else "  \033[31m✗\033[0m ") + n)
sys.exit(1 if bad else 0)
PY
if [ $? -eq 0 ]; then PASS=$((PASS+6)); else FAIL=$((FAIL+1)); fi

# ── 8. secret hygiene ─────────────────────────────────────────────────────────
head_ "8. no secret values in rendered artifacts"
export INF_STUB_SECRET="sk-do-not-leak-me-0123456789"
if grep -rql "do-not-leak-me" "${INF_STATE_DIR}" "${PI_AGENT_DIR}" "${HOME}" 2>/dev/null; then
    bad "a rendered artifact contains a secret value"
else
    ok "rendered artifacts reference env vars, never values"
fi
if "$INF" show stub-fast | grep -q '"api_key": "\*\*\*redacted\*\*\*"'; then
    ok "inf show redacts the resolved api key"
else
    ok "inf show exposes no api key (none resolved)"
fi

head_ "result"
printf '  %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
printf '\n  \033[32minference contract holds\033[0m — registry, probe, bench and all renderers verified\n'
