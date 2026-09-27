# Native request contract

Load `scripts/workbench.lua` in the selected editor with a trusted, correctly quoted path. For example, from a native `nvim --server "$NVIM_SOCKET" --remote-expr` client, a fixed `luaeval` expression can call `dofile(<reviewed helper path>).request(<private request path>)`. Do not interpolate prompt contents into that expression. JSON request files carry text and parameters as data. Inspect the socket owner/permissions first; confirm snapshot PID, server name, and original path before mutations. No helper action creates a listener.

Lua API:

- `snapshot(bufnr)` returns the loaded normal buffer's identity, text, changedtick, modified flag, and disk fingerprint. `disk.sha256_base64` hashes base64-encoded bytes, allowing NUL-containing encodings such as UTF-16.
- `apply({expected=snapshot, original_buf=id, lines={...}})` rejects stale content, changed disk files, another editor PID, and candidates aliasing the original; preserves candidate-window reading views, replaces text, and performs ordinary `:write`. A post-save modified buffer or decoded disk/text mismatch is reported as an error requiring inspection; a mismatch marks the candidate modified because Neovim may clear that flag after a `BufWritePost` edit. A failed write leaves changes visible for inspection; it does not force-write or roll back over possible plugin/user changes.
- `layout({expected_pid=pid, original_buf=id, candidate_path=path, optimizer_argv={"pi"}, cwd=path, terminal_height=10})` opens a dedicated tab with readable original/candidate splits and a visible interactive terminal. `candidate_path` must already name a separate regular file. Set `terminal_buf=id` instead of `optimizer_argv` to reuse an existing terminal; these options are mutually exclusive. No terminal input is sent. New processes strip inherited `PI_SESSION_ID`, `CDEV_SESSION*`, `PI_JOBS_DIR`, `PI_JOB_*`, `CURSOR_*`, `PI_CURSOR_*`, `MCP_*`, and `__CURSOR_*` routing bindings, then set `PI_CURSOR_LOCAL_RESUME=0` and `PI_JOB_BUS_STEER_SELF=0`. Other environment/configured provider defaults are preserved; no secret values are printed.
- `request(json_path)` dispatches a JSON object with `op` equal to `snapshot`, `apply`, or `layout`; other fields match the APIs above (`buffer` selects a snapshot). It returns JSON. Optional `output_path` reserves a new mode-0600 result file before dispatch and returns a compact receipt; choose a new file for each snapshot rather than overwriting evidence. Operation failures leave an error receipt and propagate the error. A later receipt-write failure returns an explicit completion/error status requiring inspection before any retry; it does not imply the operation was rolled back.

Example data (replace numeric identities and paths from the live snapshot):

```json
{"op":"snapshot","buffer":9,"output_path":"<private_snapshot_path>"}
```

```json
{"op":"apply","expected":"<replace with snapshot object>","original_buf":1,"lines":["A revised prompt line."]}
```

The second example is schematic: `expected` must be the actual JSON object, not its filename/string. Apply never changes the buffer's path. It requires a distinct original buffer and checks filesystem identity to catch symlink/hardlink aliases. Guards detect observed stale state; they do not lock external writers or contain editor plugins. Normal save autocmds can still run, and the returned snapshot is the evidence of what was saved.

Before dispatch, give an optimizer a bounded context packet: intent/invariants; snapshot revision; sources and uncertainty; owned output/diff; dependencies and permission/budget limits; completion evidence. Reuse captured research before launching gap-filling work. Separate design associations from hard execution prerequisites. Keep runtime/provider choices explicit; no tool allowlist or prompt-only budget should be described as enforced containment.

Validation from the skill directory:

```sh
nvim --headless --clean -i NONE -l tests/workbench_spec.lua
```

This uses only disposable buffers/files and `cat` and synthetic native-Neovim terminal fixtures; it does not launch Pi or touch a live editor.
