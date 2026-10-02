# aos-model — model-profile.v1 tooling

`render` turns a `model-profile.v1` JSON profile into a harness-native config
fragment. Dry by design: it never writes config files. `--apply` is NOT
implemented (wave 1); passing it is a usage error (exit 2).

## Usage

```bash
aos-model render --harness pi|hermes|claude <profile.json|->   # fragment on stdout
aos-model render --check <profile.json|->                      # verdict on stdout
```

- Profile is a file path or `-` (stdin). Typed stdin rejection on schema mismatch.
- Profiles are always validated against `config/aos/model-profile.v1.schema.json`
  before rendering; `--check` validates only (mutually exclusive with `--harness`).
- Extra fields are allowed only with an `x_` prefix (frozen contract).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | profile/render failure (typed JSON error on stderr; stdout stays clean) |
| 2 | usage error |

## Fragments (stdout, single JSON object)

| Harness | kind=single | kind=moa |
|---------|-------------|----------|
| pi | `{defaultProvider, defaultModel, enabledModels}` | typed error `moa_unsupported_harness` |
| hermes | `{llm:{provider,model}, fallback_model:[]}` | `{llm:{provider:"moa",model}, fallback_model:[], moa:{proposers,aggregator,rounds}}` (provider moa overlay) |
| claude | `{args:["--model", <model>]}` | typed error `moa_unsupported_harness` |

- pi `enabledModels` is `[<model>]`; merging with existing settings is the
  applier's job (`--apply`, not wave 1).
- hermes `fallback_model` is `[]`: a single profile fragment declares no
  fallback; the applier may merge fallback-rung profiles.
- Rendering is additionally gated on `harness_support.<harness> == true`
  (typed error `harness_unsupported`).

## Stderr error codes (exit 1, single JSON line)

| Code | Meaning |
|------|---------|
| `invalid_json` | profile input is not valid JSON |
| `schema_validation` | profile rejected by model-profile.v1 schema (`errors` list attached) |
| `moa_unsupported_harness` | kind=moa rendered for pi/claude |
| `harness_unsupported` | profile's `harness_support` is false for the target harness |
| `input_unreadable` | profile file cannot be read |
| `schema_unavailable` | schema file missing/invalid |
| `validator_unavailable` | `jsonschema` module missing |

## Tests

```bash
python3 -m unittest tests/test_aos_model_render.py
```