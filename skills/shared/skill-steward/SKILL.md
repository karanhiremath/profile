---
name: skill-steward
description: Add, remove, move, or debug skills for any agent harness (claude, codex, pi) through the skill-steward manifest instead of copying or symlinking skill folders by hand. Use when installing a skill globally, when a harness warns about a skill at startup, when a skill link is broken or stale, or before running `cp -R`/`ln -s` into ~/.claude/skills, ~/.codex/skills, or ~/.pi/agent/skills.
---

# skill-steward

Harness skill dirs are generated state. The manifests are the source of truth:

- `~/.config/skill-steward/manifest.toml` — personal/tool skills (profile repo, `config/skill-steward/manifest.toml`)
- `~/.config/skill-steward/manifests.d/*.toml` — overlays (work skills live in a work-owned overlay, never in profile)

Skills link into pinned, detached worktrees at `~/.local/share/skill-steward/sources/<source>`, never into a primary checkout or a feature worktree.

## Rules

- Never `cp -R` or `ln -s` into a harness skills dir. Add a `[[skill]]` entry, then sync.
- Never delete a harness entry. `sync --prune` moves undeclared entries to `~/.local/share/skill-steward/quarantine/<ts>/`.
- A skill that only exists on an unmerged branch gets its own `[sources.<name>]` pinned at that branch, with a comment saying when to drop it. After merge, repoint it at the default-branch source.
- Entries owned by another installer (claude.ai sync, plugin/MCP installers) go under `[external]`; the steward never touches them.
- Keep loading minimal: declare a skill only for the harnesses that need it. Project-scoped skills (`<repo>/.claude/skills`) stay in their repo; only declare them globally when needed outside that repo.

## Commands

```bash
skill-steward audit                 # read-only JSON; exit 1 on findings
skill-steward sync                  # plan (JSON), changes nothing
skill-steward sync --apply          # refresh sources, link/relink, drop dangling links
skill-steward sync --apply --prune  # also quarantine undeclared entries
skill-steward hook                  # SessionStart: silent when clean
```

`just skills-audit` / `just skills-sync` from the profile repo wrap the same commands.

## Adding a skill

```toml
[[skill]]
source = "profile"            # a [sources.*] key
path = "skills/pi/my-skill"   # dir containing SKILL.md, relative to the source root
harnesses = ["codex", "pi"]
# name = "..."               # only if the link name differs from the dir name
```

Then `skill-steward sync` (review the plan) and `skill-steward sync --apply`.

## Finding kinds

| kind | meaning | sync action |
|---|---|---|
| `missing` | declared, not present | link |
| `broken-link` | dangling symlink | relink if declared, remove if not |
| `drift` | link points somewhere other than the pinned source | relink |
| `copy` | real dir shadows a declared skill | quarantine copy, link |
| `unmanaged` | present, undeclared, not external | quarantine only with `--prune` |
| `invalid-skill` | bad/missing frontmatter, description > 1024 chars | none — fix the skill |
| `duplicate-name` | two entries resolve to the same frontmatter `name` | none — pick one |
| `source-missing` / `source-stale` / `source-dirty` | pinned worktree absent / behind ref / has local edits | create / advance / leave alone |
