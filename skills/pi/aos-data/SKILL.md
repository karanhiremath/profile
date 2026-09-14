---
name: aos-data
description: ao0 vault toolkit — portable Rust CLI/TUI for personal notes and work kh Obsidian ledgers.
---

# aos-data

Lane **ao0** (data / corpora / two-ledger vault IO). Sibling of `aos` (install),
`aop` (procedures), `infra-*`. Does not fold into `aos`.

Binary lives in profile (`bin/aos-data`). Vaults hold manifests only.

```
notes                  # personal TUI  (~/src/notes or $PERSONAL_NOTES_ROOT)
kh                     # work TUI      (~/src/karan.hiremath or $WORK_NOTES_ROOT)
aos-data --vault PATH  # explicit
notes status --json
notes daily --open
notes capture --to inbox 'idea'
kh capture --to daily 'shipped x'
aos-data search QUERY --json
```

Install: `just aos-data` or `bin/aos-data/install`.

## Boundary

- `notes` only loads `class = personal`. Never copy work-private detail.
- `kh` only loads `class = work`. Work vault may be absent on a personal host.
- Bridge schema is the only automatic work→personal payload (load / category / impact / next).
- Writes stay inside the resolved vault root. Never `tmux send-keys`.
- Open files with `$VISUAL` / `$EDITOR` / nvim.

## Do not rebuild

session-ledger-daily, work-notes-librarian, personal-notes-steward, atop, pc.
This binary is vault IO + TUI. Ledger collect stays those SOPs.
