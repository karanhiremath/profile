# AOS voice conference - offline spike

**Fake only. No remote discovery, microphone, audio playback, managed-agent
connection, live harness dispatch, or terminal renderer is enabled.**

An operator conference binds an exact host / tmux server / session / window /
pane / harness-session generation. A simulated Cartesia managed-agent callback
cascades through the bound controller → PM → PL → worker route. Plain shell
panes support simulated status/observe only; they never receive typed commands.

## Run from the repository root

Requires `uv` and an already installed Python 3.12. Launchers are offline and do
not download an interpreter or dependencies. No host installation is needed.

```bash
PROFILE_DIR="$PWD" ./bin/aos voice doctor
just aos-voice-test
just aos-voice-demo
```

The demo emits one JSON conference with `receipt.status=simulated`,
`receipt.executed=false`, and simulated acknowledgements. It does not dial in.
`just` may print its recipe to stderr; CLI stdout remains one JSON object.

Equivalent pipeline:

```bash
./bin/aos-voice/aos-voice targets --catalog bin/aos-voice/fixtures/catalog.json \
  | ./bin/aos-voice/aos-voice bind --fake --domain personal \
      --target remote-worker --generation 3 \
  | ./bin/aos-voice/aos-voice join --fake \
  | ./bin/aos-voice/aos-voice dispatch --fake \
      --request bin/aos-voice/fixtures/request.json \
  | ./bin/aos-voice/aos-voice leave --fake
```

`connect`/`disconnect` alias `join`/`leave`. Mutating stages require exactly one
of `--fake` and `--dry-run`. Dry runs do not alter bindings, connection state or
replay history. Help goes to stderr. Errors produce bounded JSON plus constant
human diagnostics, never the rejected input.

For a separately installed development CLI (explicit local installation):

```bash
uv tool install --offline -e ./bin/aos-voice
```

Do not install or synchronize this spike into live Cos/CosW profiles as a live
voice backend. The package console entry point is `aos-voice`; `aos voice` uses
the source-checkout launcher.

## Agent-facing interface

- `status`, `doctor`: static capability report; `live_ready=false`.
- `targets`: fixture catalog from structured stdin or `--catalog`; not fleet discovery.
- `bind`: explicit domain, target ID and generation; pin the full cascade.
- `join`/`leave`: fake conference lifecycle, not process attach/detach.
- `dispatch`: bounded, enumerated fake tool callback. No freeform shell verb.
- `renderer`: fake byte/resize adapter report; not a loaded libghostty renderer.

Pipeline state is **unsigned test data, not authenticated authority**. Replay
protection is only within the supplied state; resetting/editing state bypasses
it. A live adapter must use canonical identity, registry, capabilities and
server-side replay storage, not trust this JSON as a bearer credential.

Optional file-only events use `CARTESIA_EVENT_SINKS`, `CARTESIA_EVENT_BUSES`, or
`CARTESIA_EVENT_BUS`. The only offline profile is `CARTESIA_EVENT_PROFILE=none`.
No sink is enabled by default. See [CONTRACT.md](CONTRACT.md).

## Remaining live gates

1. Resolve the maintained owner of the historical voice PWA; do not deploy its
   unversioned reference copy or replace an occupied service port.
2. Verify the managed-agent connection/tool API and approved domain endpoint.
3. Connect canonical authenticated session discovery, ACK and harness adapters.
4. Verify libghostty/WASM source, commit, license, browser API and terminal fidelity.
5. Obtain separate approval for identity/token provisioning, local microphone
   capture, deployment and a single remote-host canary.

Desktop Ghostty remains a separate native client. This spike changes neither
Ghostty's palette/keybindings nor any running tmux or agent process.

## Additional validation

From `bin/aos-voice` (requires already cached build/lint tools):

```bash
uv lock --offline --check
uvx --offline ruff check src tests run.py
uvx --offline ruff format --check src tests run.py
uv build --offline
```

See [SOURCE-MAP.md](SOURCE-MAP.md) for reuse boundaries and
[CONTRACT.md](CONTRACT.md) for the fake wire protocol. Optional zsh completions
are in `completions/_aos`; Bash completions are in `completions/aos.bash`.
Neither is installed automatically.
