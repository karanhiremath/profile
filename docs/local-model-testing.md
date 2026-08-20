# Local Model Testing SOP

Principle: a backend is declared once and proven before anything is bound to it.

Every harness here — pi, hermes/herm-tui, cursor-agent, claude, codex — used to
carry its own hardcoded provider/model pair. Swapping in a local model meant
editing each one and hoping they agreed. The inference registry replaces that
with one declaration per backend and a renderer per harness.

## The three tools

| Tool | Declares | Command |
|---|---|---|
| `inf` | inference backends (local + hosted) | `just inference` |
| `sbx` | project sandboxes and JIT access | `just sandbox` |
| `loop` | backlog dispatch to coding agents | (no install; run in place) |

## Everyday flow

```bash
inf list                      # what exists; * marks the registry default
inf doctor                    # what THIS machine can actually run
inf up dflash2-qwen-llamacpp --build
inf probe dflash2-qwen-llamacpp     # does it satisfy the harness contract
inf bench dflash2-qwen-llamacpp     # speedup vs its autoregressive baseline
inf bind pi dflash2-qwen-llamacpp --only --probe
```

`--probe` refuses to bind an unhealthy backend. Prefer it: binding a dead
endpoint into pi produces a confusing failure at first use rather than now.

Point a Hermes agent at a backend in any of three ways, highest precedence
first:

```bash
agents up cosw --backend dflash2-qwen-llamacpp   # this launch only
agents backend dflash2-qwen-llamacpp             # global, all agents
# or in the profile yaml:  llm: { backend: dflash2-qwen-llamacpp }
```

An unresolvable backend warns and falls through to the profile's literal
`llm.provider`/`llm.model`, so a missing registry never strands an agent.

## The harness contract

`inf probe` asserts the five things a harness actually depends on. It fails
closed — a backend that misses any of the hard checks is reported unusable.

| Check | Why it is in the contract |
|---|---|
| `health` | is anything listening |
| `models` | does `/v1/models` list the `served_name` the registry claims |
| `chat` | blocking completion returns content |
| `stream` | SSE arrives **and terminates with a `finish_reason`** |
| `agent-turn` | `stream: true` **with** `tools`, `max_completion_tokens`, `stream_options` |
| `tools` | `tool_calls` come back when the backend declares tool support |

The last two exist because of a bug this SOP was written after. A backend passed
`stream` and `tools` individually and was declared conformant; pi then failed
every turn with `Stream ended without finish_reason`. Two lessons, both now
enforced:

- **Counting SSE chunks is not enough.** A stream must terminate with a chunk
  carrying `finish_reason`, or clients fail the turn.
- **A coding agent never sends the simple shapes.** It sends streaming *and*
  tools *and* `max_completion_tokens` on every turn. Backends commonly handle
  those separately and answer the combination with a non-SSE body.

If you add a backend that passes `inf probe` but a harness still fails, the
contract is incomplete again. Reproduce it against the stub with
`--log-requests`, add the missing assertion to `probe`, and add a fixture that
fails without the fix — that is how both of the above were found.

## Speculative decoding (DFlash 2)

DFlash 2 pairs a small **drafter** with the **target** model: the drafter
proposes a block of tokens in parallel, the target verifies them in one forward
pass. So a speculative backend is only meaningful against the same target
running autoregressively. Every `dflash2-*` backend declares a
`baseline_backend` identical to it except for the `--spec-*` flags, and
`inf bench` reports a speedup only when it measured that control:

```bash
inf up qwen-llamacpp-baseline --build     # the control
inf up dflash2-qwen-llamacpp              # the speculative one
inf bench dflash2-qwen-llamacpp --runs 5 --out bench.json
```

A speculative number without its baseline is reported as meaningless rather
than printed as a win.

### Picking a runtime

The upstream flags differ per runtime and are **not** interchangeable. They are
transcribed per backend in the registry; do not normalize them.

| Target | Backend | Notes |
|---|---|---|
| Apple silicon | `dflash2-qwen-llamacpp-metal` | **Native build**, not a container |
| Apple silicon (GUI) | `dflash2-qwen-omlx` | prebuilt DMG, configured in Model Manager |
| Linux + NVIDIA | `dflash2-qwen-llamacpp` | CUDA container, llama.cpp PR #27342 |
| Linux + NVIDIA | `dflash2-qwen-vllm` | vLLM PR #52816, one JSON `--speculative-config` |
| Multi-GPU | `dflash2-glimmer-sglang` | the post's reference config |
| Host build | `dflash2-qwen-ollama` | needs a source build of the dflash2 branch |

**Do not run llama.cpp in a container on macOS.** podman on macOS is a Linux VM
with no Metal access, so a 27B model falls back to CPU and loses far more than
speculative decoding wins back. Use `bin/inference/build-llamacpp-metal`, which
verifies the built binary actually advertises `--spec-type` before claiming
DFlash support.

**Capacity.** Qwen3.8-27B is ~54GB at bf16 and will not fit a 24GB card (an L4).
The vLLM backend therefore defaults to 4-bit AWQ (~15GB) leaving room for the
drafter and KV cache. On an 80GB card, clear `model.quantization` and raise the
memory fraction.

## Sandboxes and JIT access

`sbx` is **not a sandbox runtime**. It is the lease/governance and toolchain
layer in front of one, and it delegates isolation:

| `executor` | Isolation by | Used for |
|---|---|---|
| `agent-sandbox` | `scripts/agentic/agent-sandbox` — scratch-backed, rootless podman/enroot/apptainer, no host secrets, network off by default | work-boundary sandboxes |
| `direct` | a hardened container `sbx` composes itself | public sandboxes, CI runners, any host with no existing primitive |

`auto` (the default) delegates work-boundary sandboxes and keeps public ones
`direct`, because `agent-sandbox` requires a `/scratch/people/$USER` root that
only the work machines have.

That split is deliberate.
`karan.hiremath/agentic/memory/projects/agent-sandbox-consolidation.md` records a
standing decision **not to start a new sandbox primitive** — secure agent
execution is largely built on cartesia-security PR #42
(`tools/cdev/src/cdev/isolation/`), and a third parallel implementation would
orphan it. So `sbx` adds the two things that note lists as missing — JIT
credential scoping and an access audit trail — and hands isolation to the
runtime that already exists. Setting `executor = "direct"` on a work-boundary
sandbox is exactly the mistake that decision prevents, and `sbx validate` warns
about it.

**Audit format caveat.** The local hash-chained ledger is interim. The same note
requires sandbox lifecycle events to emit `cagent.audit.AuditEvent` with a
`frameworks/<fw>/evidence-map.yaml` entry rather than a new format. When that
lands, this ledger becomes a local mirror rather than a second source of truth.

Access is a lease, not a state. The failure mode this prevents is not a breach —
it is a sandbox opened for one afternoon that is still open weeks later with a
token in it.

```bash
sbx list                      # sandboxes, boundaries, lease state
sbx inflight                  # registered projects vs open leases
sbx grant local-model-lab --reason "DFlash2 throughput comparison" \
    --ttl 4h --project local-model-testing --env HF_TOKEN
sbx up local-model-lab
sbx shell local-model-lab
sbx revoke local-model-lab --down
sbx audit                     # who had access, when, why
```

Two-key rule for secrets: a variable is forwarded only if it is in the
sandbox's `allow_env` **and** named in an unexpired lease. `sbx` never writes a
secret to disk.

The audit log is hash-chained; `sbx audit` reports if records were edited or
removed. If it says the chain is broken, stop and find out why before granting
anything.

Governance runs through `agents up sandbox-warden`, which can grant and revoke
but deliberately cannot widen an `allow_env` ceiling or disable a lease
requirement — those are reviewed changes to a committed spec.

## Data boundary

`config/` here is public and lives on both machines. Work-only backends and
sandboxes belong in the work overlay, which is first on both search paths:

```
~/src/karan.hiremath/agentic/inference/backends.toml
~/src/karan.hiremath/agentic/sandbox/sandboxes.toml
```

`inf validate` and `sbx validate` reject an internal hostname or a
work-boundary sandbox declared in the public registry. Registry files hold env
var **names**, never values.

## When something is wrong

```bash
inf doctor <backend>        # missing prerequisite, unset token, wrong platform
inf status                  # what is running, what is answering
inf show <backend>          # the fully resolved spec, key redacted
sbx audit                   # access history and chain integrity
loop status                 # budget, running workers, recent ticks
```

`doctor` is deliberately honest: it reports a missing GPU or an unset
`HF_TOKEN` rather than claiming readiness. For a `[.manual]` backend (oMLX,
Ollama's dflash2 branch) it reports whether the endpoint is answering, because
there is nothing on the host it can check.
