# AOS filter + policy engine

First-class AOS primitive (`aos.policy.v1`). One document set drives
filters and transforms on:

- inbound / outbound byte streams
- context and memory
- selected tools, skills, extensions, prompt primitives, harness primitives
- CoT / MoA between collaborative harness wrappers
- graph-eng / fleet-eng edges and node introspection points

Silent rules mutate those surfaces and never emit policy language into
CoT, MoA, or human-visible tokens.

## Layout

| Path | Role |
|---|---|
| `schema.yaml` | contract |
| `bundle.yaml` | load order + overlay |
| `policies/` | committed policies |
| `adapters/` | Cursor / Claude / Codex / pi / Hermes / graph compile maps |
| `acl/grants.yaml` | who may mutate policies |

Runtime overlay and compiled sidecars: `~/.local/share/aos/policy`.

## Operator

```
aos policy list
aos policy apply --wrapper herm-tui --provider cursor
aos policy eval --surface catalog.tools --wrapper herm-tui --provider cursor
aos policy grant --agent worker --capability policy.write --ttl 2h --class orchestrator --agent cosw
```

`put` / `grant` require a matching ACL or JIT grant. Bundled
`herm-tui-cursor-exclusive` is the Cursor-model seat policy: Hermes tools
only, remapping invisible.

Spend (CAI-AOS): `just aos-spend ledger` after
`aos-spend ingest-cursor-csv --csv <export.csv>`. Dashboard `Cost=Free` is
included quota. Price input/output/cache from the token-fee table.
