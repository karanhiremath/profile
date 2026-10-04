# cos-voice-wasm

First Cos-voice apply crate. Dest allow-list, steer envelope, inventory,
`fleet|otel|pane` view selection, and a chip/supervisor stub. Host effects
(tmux capture, HTTP) stay in `cos-voice-host`. The same apply crate also
builds as `wasm32-wasip1` (WASI command) and `wasm32-wasip2` (WIT component
for Elixir Wasmex).

## Paths

- Crate: `/Users/karan/src/profile/bin/cos-voice-wasm/`
- WASI module: `target/wasm32-wasip1/release/cos-voice-apply.wasm`
- WIT component: `target/wasm32-wasip2/debug/cos_voice_wasm.wasm` (`wit/world.wit`)
- Apply host: `127.0.0.1:8788` (`COS_VOICE_WASM_BIND`)
- Phone/PWA loopback: `127.0.0.1:8787` (Termix `:18787 → :8787`)
- Elixir supervisor: `elixir/` (`CosVoice.Wasm` → Wasmex.Components)

## Commands

```bash
cd ~/src/profile/bin/cos-voice-wasm
cargo test
cargo build --bins
cargo build --bin cos-voice-apply --target wasm32-wasip1 --release
cargo build --lib --target wasm32-wasip2
./target/debug/cos-voice-apply s2s --dest cos
./target/debug/cos-voice-host s2s --dest oma-s
./target/debug/cos-voice-host capture ao2:0.0
./target/debug/cos-voice-host serve --bind 127.0.0.1:8788
cd elixir && mix deps.get && mix test
```

The wasm module itself does not open sockets. `cos-voice-host` binds
`127.0.0.1` only. Cos / `cos-*` / `atop*` panes are denied.
