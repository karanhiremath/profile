# aos-policy-engine

In-process AOS filter + policy evaluator for pi / herm-tui.

Author documents live in `config/aos/policy`. Compile them with
`aos policy apply` (requires an orchestrator or JIT grant) to
`~/.local/share/aos/policy/compiled/resolved.json`. This package reads
that snapshot and:

- filters `catalog.tools` before the model starts
- silently strips remapping language from system prompt / outbound / CoT / MoA
- rewrites exact TTS stall / Cos-timeout sentences to continuation phrases (`stream.tts`)
- exposes `aos_policy` as a count-only tool (silent rule bodies stay out)
- exposes `aos_voice_brief` / `aos_voice_filter` for Cos-voice (no local LLM)

The Python CLI in `bin/aos-policy` is the source-of-truth engine and
adapter compiler for Cursor, Claude, Codex, Hermes, and graph-eng edges.
