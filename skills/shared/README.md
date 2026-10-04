# Shared agent skills

This directory is the canonical source for portable user-level skills that
should behave consistently across supported agent runtimes. Keep machine
credentials, private work context, and generated runtime state out of it.

Install every skill with:

```bash
bin/agent-skills/install
```

The installer creates conservative symlinks for Codex, Cursor, Claude, Pi, and
Hermes. It is idempotent and refuses to replace an existing non-matching path.
Use `--dry-run` to inspect destinations or `--target NAME` to select one
runtime. Run `bin/agent-skills/install --help` for all options.

`dia-browser` is installed but hidden from the model catalog
(`disable-model-invocation`). Invoke it with `/skill:dia-browser` when needed.
Do not treat it as a default autoload skill.

Profile-managed Hermes materialization links these skills into new isolated
profile roots and their named runtime homes. Rerun the installer for Hermes
homes created by other tooling.
