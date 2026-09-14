# aos-data

Portable ao0 vault toolkit. One Rust binary, two argv0 faces:

| argv0 | vault | class |
|---|---|---|
| `notes` | `$PERSONAL_NOTES_ROOT` or `~/src/notes` | personal |
| `kh` | `$WORK_NOTES_ROOT` or `~/src/karan.hiremath` | work |
| `aos-data` | `--vault` or cwd `aos-data.toml` | from manifest |

Install: `just aos-data` from this profile worktree.

Commands: `status`, `daily`, `inbox`, `capture`, `search`, `tui`, `doctor`.
`--json` is structured stdout. Open uses `$VISUAL`/`$EDITOR`/nvim. Never send-keys.
