# Voice integration reuse map

Generic source ownership and implementation status; no live hosts or identities.

| Owner / source | Existing seam | Spike decision |
|---|---|---|
| `profile/bin/aos` | Personal AOS command dispatcher | Add `voice` subcommand; no daemon or new bus |
| `profile/bin/hermes/agents`, `hermes_agents.py` | Profile resolution and isolated agent homes | Reuse later; do not materialize homes or credentials during the spike |
| `profile/bin/hermes/plugins/cartesia` | STT/TTS providers | Existing providers are not proof of managed-agent API integration |
| Herm `src/voice/useVoice.ts` | `voice.toggle`, `voice.record`, session IDs and stale-response handling | Reuse live voice RPC/events after explicit integration review |
| Hermes Agent `hermes_cli/voice.py` | Runtime-owned recording API | Operator-device capture needs a separate local client for remote sessions |
| Historical Cos-voice PWA reference | xterm.js, WebSocket PTY bridge, Rust/WASI apply contract | Reference only; maintained owner/deployed state unresolved; do not copy wholesale |
| Desktop Ghostty native scripting | Stable window/tab/terminal IDs | Separate native UI client; no assumption that WASM loads into installed Ghostty |
| Proposed libghostty/WASM renderer | Source/API/license not available in inspected sources | Gate remains unverified; implement only opaque byte/resize seam now |
| Proposed managed voice-agent adapter | Project/deployment and approved API not resolved | Fake tool callbacks only; no provider SDK, auth or service calls |

Generic offline contracts belong here. Project-specific policies, work endpoint
selection, managed-agent deployment IDs and credentials do not belong in this
repository. Do not relax a personal voice domain's work-profile denylist to make
CosW reachable; integrate a separately approved work-domain surface.

No maintained libghostty/WASM build or real managed-agent adapter was identified
in the inspected local seams. The spike does not claim compatibility, a working
browser terminal, live remote conferencing or verified endpoint access.
