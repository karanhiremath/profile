# cmdk — layered action bar

One catalog drives Ghostty Cmd-K, tmux popup, zsh completions/fzf, nvim, and
harness/OTEL hooks. Do not invent a second attach grammar. Attach still goes
through `attach` / `sesh` / `tc` ([Attach SOP](../../../skills/shared/attach/SKILL.md)).

## Layers

```text
Ghostty Cmd-K
    → tmux display-popup (existing client)
        → zsh picker (fzf)
            → run in zsh
            → inject into a harness prompt buffer
            → OTEL / metrics lane
            → nvim sibling pane (pc layout)
```

| Layer | Hook | Notes |
|-------|------|-------|
| `ghostty` | `command+k` → `cmdk-ghostty` | Native palette has no custom entries. New tab hands off to tmux popup. |
| `tmux` | `prefix+k` / `cmdk popup` | `display-popup` on the active client. Status chip on the right. |
| `zsh` | `cmdk`, `^X^K`, completions | Plugins + fzf + catalog completions. Prompt shows session/layer. |
| `nvim` | `<leader>k` | Opens the same tmux popup. pc panes stay `nvim / pi / zsh`. |
| `harness` | `cmdk inject` | Prompt-buffer only. **Never** `send-keys` into Cos / `cos-*` / Atop. |
| `otel` | `cmdk otel` | Prefer Cos-voice `POST /view {view:otel}`; else focus a metrics pane. |

## Send-keys policy

Copied from `bin/ghostty-voice/lanes.py` (source of truth for voice/AOS):

- Allowed: worker sessions `ao0`–`ao4`, `infra0`–`infra4`; `pi_*` pc harness panes
- Blocked: `cos`, `cos-*`, `atop*`, `notes`, `pm`, `pl`, `cosw`, dest aliases

Cos / plan / Atop get inbox / `atop steer`, not tmux input-buffer.

## Commands

```bash
cmdk                 # fzf picker
cmdk pick
cmdk popup           # tmux display-popup
cmdk status          # JSON
cmdk status --tmux   # fast one-liner for the tmux bar
cmdk status --prompt # zsh prompt chip
cmdk layer           # detect current pane layer
cmdk list            # catalog + live sessions (tsv)
cmdk run <id>
cmdk inject [--target T] [--text ...]
cmdk otel
cmdk classes         # pi profile classes from manifests/profiles.json
```

## Files

| Path | Role |
|------|------|
| `catalog.json` | Static actions (`profile.cmdk.v1`) |
| `bin/cmdk/cmdk` | zsh driver |
| `bin/cmdk/lib.py` | detect / list / dispatch / inject |
| `zsh/cmdk.zsh` | widget + `piclass` |
| `zsh/{plugins,fzf,completions,prompt}.zsh` | shell stack |

Add actions to `catalog.json`. Dynamic rows (tmux sessions, fleet lanes, profile
classes) come from `lib.py` at pick time.
