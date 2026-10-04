# Ghostty voice harness (AOS)

Loopback PWA + host harness. Bind `127.0.0.1:8787` only. Cartesia keys stay on the host (`~/.local/share/hermes-agents/chief-of-staff/profiles/chief-of-staff/.env`). Never log or return the key. Tailscale Serve maps `https://karans-mac-mini.tail1e8436.ts.net:8787` → this port. Phone wasm tunnel dest is Termix `:18787` → `:8787`.

## Cos-voice dest

Default dest is **Cos** (`cos` / `cos-voice`). Spoken aliases map to Cos: `caws` (Ink-2 hears “Cos” this way), `coz`, `kos`, `chief`, `chief of staff`, `C-O-S` / `COS`. Spoken cues say **Chief of Staff**, never the STT token. Talk writes the Cos Hermes inbox and calls `atop steer --harness hermes`. That is persist + optional live steer. `delivered=false` when only the inbox was written.

**Voice mode** (PWA `Voice` toggle) is a conversation loop: listen (Ink-2) → finalize on silence → steer + Cookie/Sonic TTS → listen again. Hold-to-talk still works as a barge-in / cut. Do not treat voice mode as hold-and-release only.

**Never `tmux send-keys` into Cos, `cos-*` plan panes, or `atop*`. ** Worker panes `ao0`–`ao4` / `infra0`–`infra4` may receive input-buffer `send-keys` (full prompt) or a single TUI pick key.

| Dest | Transport | send-keys |
|------|-----------|-----------|
| `cos`, `cos-voice`, `chief` | Hermes inbox + `atop steer --harness hermes` using the live Cos session id (`lastSessionId` / `COS_VOICE_SID`). Pane values (`tmux:cos:0.0`) are rejected | never |
| `this`, `pi` | `atop steer --harness pi` | never |
| `claude` | `atop steer --harness claude-code` | never (workers still may) |
| `pm`, `pl`, `notes` | Hermes inbox + `atop steer --harness hermes` / `herm-tui` | never |
| `ao0`–`ao4`, `infra0`–`infra4` | compact prompt → `atop steer --harness claude-code --sid tmux:{session}:0.0` **and** `tmux send-keys -l` input-buffer | yes |
| `cos-ao*`, `cos-infra*` | inbox / `atop steer` only | never |
| `brief` or brief-like transcript | fleet spoken + TTS | never |
| `buffer` / congress / draft | append dest session `prompt.md` via `~/.pi/agent/buffers/INDEX.jsonl` | never |
| `cosw` | blocked on this personal host | never |

If the transcript names a lane (`ao2 …`, `infra0 …`) route there even when dest is Cos, and also keep a copy in the Cos inbox.

## AOS lanes (hiremath fleet)

| Lane | Family | tmux sessions | Attach |
|------|--------|---------------|--------|
| ao0 | data | `ao0`, `cos-ao0` | `sesh connect ao0` / `attach mac` then switch |
| ao1 | model | `ao1`, `cos-ao1` | `sesh connect ao1` |
| ao2 | harness | `ao2`, `cos-ao2` | `sesh connect ao2` |
| ao3 | graph | `ao3`, `cos-ao3` | `sesh connect ao3` |
| ao4 | fleet | `ao4`, `cos-ao4` | `sesh connect ao4` |
| infra | infra | `infra0`–`infra4`, `cos-infra0`–`4` | `sesh connect infra0` |
| mac | host | `mac` | `attach mac` / `sesh connect mac` |
| oma | peer | `home` on Omarchy | `attach oma-default` |
| oma-s | sandbox | podman tmux on Omarchy | `attach oma-s` |
| mac-s | sandbox | podman tmux on this host | `attach mac-s` |

Do not invent `workmux` — there is no binary. Harness aliases are `attach`, `sesh`, and `tmux-connect` (`~/src/profile/bin/tmux/interactive`, `tmux-connect`, `hosts/registry.conf`).

## HTTP API (`127.0.0.1:8787`)

- `GET /` `GET /manifest.json` — PWA
- `GET /health` — `{ok, listen, cartesia_key: present|missing, lanes, target, lane, dest, view, views, pane_target, stt_mode, stt_model, stt_sessions, apply}`
- `apply` — sidecar status for ao2's `cos-voice-wasm` (`via=http|cli|python-fallback`). Host may listen on `127.0.0.1:8788`. This process stays on `:8787`. Do not replace the crate. Crate `s2s` / `GET :8788/s2s` is dest+Hermes-profile+Cartesia **plan only**. It does not call Cartesia, bounce this loopback, or change `/stt` `/tts`. Elixir `CosVoice.s2s/1` prefers the WIT component via Wasmex.Components; native `cos-voice-apply` is fallback only. Python is not on that apply path.
- `GET /lanes` — lane catalog + live tmux attached/window counts
- `GET /fleet` — `fleet.snapshot()` plus `spoken`. Includes `hosts`, `jobs`, `work` / `plan` / `infra` / `operator` / `sandboxes`, and `graph.gates` when `dependency-dag.md` parses (gate id / owner / state only).
- `GET /layers` — phone cards: `{ok, layers:[{id,title,summary,cards:[{title,meta,state,detail}]}], agents:[{id,session,family,role,live,blocked,title}], prompts:[{target,kind,options}]}`. Prompts are detected from a short capture of **worker panes only**.
- `GET /view` `POST /view` — Cos-voice display `{view: fleet|otel|pane, dest?, target?}`. Pane **watch** includes Cos (`cos:0.0`) plus workers. Session picker POSTs dest+target so the TTY and steer dest change together. Snapshot includes `buffer` (congress/`prompt.md` tail or last steer) and `prompt` (real TUI choices on the **current worker only**; no generic yes/no/1234 pad). `cos-*` / `atop*` stay blocked. Send-keys still never Cos/Atop; transcript goes to dest harness (inbox for Cos, input-buffer for `ao*`/`infra*`).
- `GET /otel` — metrics cards from `atop dump` + `~/.pi/agent/otel` counts. No raw_ref / session dumps. No second collector.
- `GET /ghostty` — windows/tabs/splits inventory (best-effort on macOS)
- `GET /pane?target=SESSION:WIN.PANE` — `{text}` from `tmux capture-pane -p -J` (blocked on Cos/atop and non-workers). `?esc=1` returns an ANSI `PaneFrame` (`text`, `plain`, `seq`, `cols`, `rows`) for xterm.js.
- `GET /brief` is not used; `POST /brief` speaks the fleet snapshot
- `POST /stt` — raw audio body → `{ok, transcript, model, endpoint}`. Fallback only. **Ink 2** (`ink-2`) hold-to-talk streams PCM **while held** via `/stt/open` + `/stt/chunk` + `/stt/finalize` to host-side `wss://…/stt/websocket?model=ink-2` (`finalize`/`close` on release). Batch `POST /stt` is **`ink-whisper` only** if the socket path is not used. Whisper is the batch fallback if the recorded-upload socket fails.
- `POST /stt/open` — opens an Ink 2 websocket session. `{ok, session, model, endpoint, mode:stream-while-hold}`.
- `POST /stt/chunk` — header `X-STT-Session`, body raw `pcm_s16le` 16 kHz mono. `{ok, bytes, total, partial?}`.
- `POST /stt/finalize` — header `X-STT-Session` → `{ok, transcript, model, endpoint, mode, bytes}`.
- `POST /stt/abort` — drop a live session without steering.
- `POST /tts` — `{text}` → `{ok, audio_b64, mime}` via Cartesia Sonic (mp3)
- `POST /steer` — `{text, dest?, target?, mode?}`. Empty text errors. Brief cues or `dest`/`mode` `brief` return `{ok, dest, spoken, audio_b64?, mime?, deliveries:[], transcript}` with no inject. Otherwise `{ok, dest, deliveries:[{target,transport,ok,note}], transcript}`. Cos inbox persist is `ok` even when Hermes HTTP `:8642` is down. Cos replies return via `POST /reply` or `steer-outbox` and are spoken on this port.
- `POST /reply` — `{text, id?, dest?}`. Cos / Hermes voice-agent return transport. Writes `steer-outbox` + TTS for the PWA. No send-keys.
- `GET /reply` — `{ok, id, dest, seq, has_text, audio_b64?, mime?}` latest Cos reply audio. Does not echo reply text.
- `POST /pick` — `{key, target?}`. Keys only: `y n Y N 1-9 Enter Escape esc`. Never a transcript. Blocked on Cos/atop. `tmux send-keys` **without** `-l`.
- `POST /attach` — `{alias}` one of attach/sesh names above
- `POST /focus` — `{session}` `tmux switch-client` for Termix/phone clients (not desktop Ghostty)
- `POST /inject` — `{text, target?}`. Worker input-buffer only; blocked on Cos/atop
- `GET /events` — SSE: lane/pane snapshot + last tts cue every ~1s. Includes `view`, `views`, `pane_target`, `workers`, `frame` (ANSI worker tail), and `otel` cards when `view=otel`. Same tunnel as the PWA (`127.0.0.1:8787`). Do not invent a second stream.

## Files

All under `~/src/profile/bin/ghostty-voice/`:

- `server.py` — stdlib HTTP, no extra deps
- `apply_host.py` — optional CLI/HTTP edge to `bin/cos-voice-wasm` (read-only; no crate edits; no `:8787` takeover)
- `fleet.py` — snapshot, spoken brief, `/layers` cards
- `steer.py` — Cos / plan inbox + atop; never send-keys Cos/atop
- `lanes.py` — catalog + tmux/ghostty/attach + worker inject/pick
- `cartesia.py` — STT/TTS, key from CoS env only (`ink-2` websocket, `ink-whisper` batch)
- `static/index.html` `static/app.js` `static/manifest.json` — iPhone PWA
- `static/vendor/xterm.js` `xterm.css` `xterm-addon-fit.js` — live pane view (libghostty web is not on this host)
- Do not commit secrets. Do not touch Termix `:8080` Serve.
