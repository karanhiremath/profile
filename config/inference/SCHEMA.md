# Inference backend schema

Field reference for `backends.toml`. Every rule below is enforced by
`inf validate`, which is a CI gate — this document explains *why* each rule
exists, since the condition alone is in the code.

Search path (first file wins per backend id, like `$PATH`):

1. `$INF_REGISTRY_PATH` (os.pathsep-separated files or dirs), else
2. `~/src/karan.hiremath/agentic/inference/backends.toml` — work overlay
3. `<profile>/config/inference/backends.toml` — generic/public

## `[defaults]`

| Key | Meaning |
|---|---|
| `backend` | used when a harness or profile names none. Must exist. |
| `fallback` | ordered candidates for `inf unbind`; every entry must exist. |
| `probe_timeout_seconds` | default `inf probe --timeout`. |
| `bench_prompt`, `bench_max_tokens` | defaults for `inf bench`. |

## `[backends.<id>]`

### Required

| Key | Values | Notes |
|---|---|---|
| `description` | prose | what it is and when to reach for it. |
| `kind` | `local` \| `remote` \| `cloud` | `local` = we start it; `remote` = someone else runs it; `cloud` = hosted. |
| `runtime` | `none` \| `ollama` \| `lmstudio` \| `vllm` \| `llamacpp` \| `sglang` \| `omlx` \| `cursor-cli` | which server implementation. |
| `api` | `openai-chat` \| `openai-codex` \| `anthropic` \| `cursor-cli` | wire protocol. Decides how `probe` and every renderer behave. |
| `model.served_name` | string | the id the server answers to, and what `/v1/models` must list. |

### Optional

| Key | Notes |
|---|---|
| `cost_class` | `free` \| `cheap` \| `metered` \| `premium` \| `unknown`. Informational; the agent loop reads it when choosing. |
| `data_boundary` | `public` \| `work`. |
| `speculative` | `true` for speculative decoding. Triggers extra required fields. |
| `template` | `true` hides it from `inf list` and blocks `inf bind`. |
| `platforms` | e.g. `["darwin-arm64"]`. `doctor` fails the host check elsewhere. |
| `notes` | free text. |

### `[.endpoint]`

| Key | Notes |
|---|---|
| `scheme`, `host`, `port`, `path` | composed into `base_url`. |
| `host_env` | env var holding the host — **or a full base URL**, which wins outright. This is how internal hosts stay machine-local. |
| `health_path` | defaults to `/health`. Ollama needs `/api/tags`; LM Studio needs `/v1/models`. |

### `[.auth]`

| Key | Notes |
|---|---|
| `api_key_env` | name of the env var holding the key. |
| `api_key_default` | fallback literal, for servers that want `none`/`ollama`. |

### `[.model]`

| Key | Notes |
|---|---|
| `served_name` | required (above). |
| `target` | the model being served. For llama.cpp this is an HF GGUF ref (`repo:QUANT`) because `-hf` resolves it directly. |
| `draft` | the drafter. Required when `speculative = true`. |
| `quantization` | runtime-specific spelling (`awq`, `fp8`, `Q4_K_M`, `4bit`, `int4`). |

### `[.speculative_config]`

| Key | Notes |
|---|---|
| `algorithm` | the runtime's own spelling: `dflash` (vLLM), `draft-dflash` (llama.cpp), `DFLASH` (SGLang). |
| `num_speculative_tokens` | 7 upstream for vLLM/llama.cpp, 8 for SGLang. The difference is upstream's, not a typo. |
| `tensor_parallel_size` | GPUs. |
| `baseline_backend` | the autoregressive control `inf bench` compares against. |

### `[.capabilities]`

`streaming`, `tools`, `reasoning_effort`, `developer_role`. These are claims the
renderers propagate (pi's `compat` block) and that `probe` checks — declaring
`tools = true` makes the tool checks mandatory.

### Launch spec — exactly one of

**`[.sandbox]`** — run it in a container.

| Key | Notes |
|---|---|
| `engine` | `auto` (podman then docker), or pin one. |
| `image`, `build_context` | if the image is absent, build from context; otherwise pull. |
| `gpus` | `none` or `all`. Maps to `--device nvidia.com/gpu=all` (podman) or `--gpus` (docker). |
| `cpus`, `memory`, `shm_size`, `ports`, `volumes` | resource and mount spec. |
| `env` | `"@NAME"` means "read env var NAME at launch". Values are never stored. |
| `args` | appended to the image entrypoint. |

**`[.native]`** — a host process. `up` is an argv list; `inf up` detaches it and
tracks the pid.

**`[.manual]`** — cannot be honestly automated. Requires `steps`; `inf up`
prints them and `inf doctor` reports whether the endpoint answers.

Placeholders expanded in all three: `{model.*}`, `{endpoint.*}`,
`{speculative_config.*}`, `{profile_dir}`, `{cache_dir}`, `{state_dir}`, `{id}`.

### `[.bindings.<harness>]`

Per-harness overrides for `pi`, `hermes`, `cursor`, `claude`, `codex`:
`provider`, `model_id`/`model`, or `unsupported = true` with a `reason`.

## Validator rules and their reasons

| Rule | Why |
|---|---|
| `description`, `kind`, `runtime`, `api` required | a backend nobody can identify gets bound by mistake. |
| `kind`/`api`/`runtime` from fixed sets | a typo would otherwise silently pick a different code path in `probe` and every renderer. |
| `model.served_name` required | it is what `/v1/models` is checked against and what every renderer writes. |
| `speculative = true` ⇒ `model.draft` | speculative decoding *is* a drafter plus a target. Without a drafter it is ordinary decoding mislabelled, and the benchmark would compare a model to itself. |
| `speculative = true` ⇒ `speculative_config.algorithm` | the flag spelling differs per runtime; there is no safe default. |
| local/remote + `openai-chat` ⇒ `host` or `host_env` | otherwise `base_url` is empty and every probe and binding silently no-ops. |
| `kind = local` ⇒ a launch spec | `inf up` would have nothing to do but would still report success. |
| `[.manual]` ⇒ `steps` | the whole point is telling an operator what to run. |
| `api_key_default` rejected if long or key-shaped (`sk-`, `xai-`, `hf_`, `csk_`) | registry files are committed. A key belongs in `api_key_env`. This is the cheap check that stops the expensive mistake. |
| internal hostname in a public registry | the data boundary. Work endpoints go in the work overlay. |
| `defaults.backend`/`fallback` must exist | a dangling default fails at bind time, far from the typo. |
| `baseline_backend` must exist (warning) | a speculative backend whose control is missing can never produce a valid speedup. |
| unknown harness in `bindings` (warning) | usually a typo that would be ignored forever. |

## Adding a backend

1. Copy `openai-compat-template`, give it a real id, delete `template`.
2. `inf validate`
3. `inf doctor <id>` — prerequisites on this machine.
4. `inf up <id>` if local.
5. `inf probe <id>` — must pass before binding anything.
6. If speculative, add its `baseline_backend` and run `inf bench <id>`.
7. `inf bind pi <id> --only --probe`
