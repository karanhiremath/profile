# gh-dash PR review

Terminal-native GitHub PR review using the off-the-shelf [`dlvhdr/gh-dash`](https://github.com/dlvhdr/gh-dash) GitHub CLI extension.

This setup intentionally uses `gh-dash` + stock `gh` instead of a bespoke PR dashboard.

## Install

```bash
gh extension install dlvhdr/gh-dash
```

If already installed, upgrade with:

```bash
gh extension upgrade gh-dash
```

The profile wrapper does this automatically when needed:

```bash
~/src/profile/bin/gh/ensure-gh-dash
```

## Direct launch

From any terminal:

```bash
~/src/profile/bin/gh/pr-review
```

which runs:

```bash
gh dash --config ~/src/profile/bin/gh/gh-dash/config.yml
```

## tmux project-review menu

The tmux shortcut launches a context-aware project-review menu, not gh-dash directly.

After installing/reloading `bin/tmux/tmux.conf`:

- `prefix P` opens the reusable menu in a tmux popup
- `prefix C-p` opens the same menu fullscreen in a tmux window

The profile tmux prefix is `C-a`, so the common shortcuts are:

```text
C-a P
C-a C-p
```

The menu starts a new tmux session with two panes:

```text
left:  Hermes project manager for the selected scope
right: live gh-dash PR dashboard
```

Available menu scopes:

- Personal project PR review: always available
- Work project PR review: shown only when a `chief-of-staff-work` Hermes profile/home is detected on the host

The left Hermes pane receives the right gh-dash pane id in `TMUX_PR_REVIEW_PANE`, so it can drive the live dashboard with `tmux send-keys` while also using `gh` commands for precise metadata/diffs/checks.

## Dashboard sections

- `My PRs`: open PRs authored by `@me` under `karanhiremath/*`
- `Needs My Review`: open PRs under `karanhiremath/*` requesting my review
- `Hermes`: open PRs authored by me in `karanhiremath/hermes`
- `Profile`: open PRs authored by me in `karanhiremath/profile`
- `Notes`: open PRs authored by me in `karanhiremath/notes`

## Useful gh-dash PR keys

Inside the dashboard, press `?` for context-aware help.

Common PR keys from gh-dash:

- `d`: view PR diff using configured pager
- `c`: comment on PR
- `C`: checkout PR locally using `repoPaths`
- `m`: merge PR via `gh pr merge`
- `w`: watch PR checks
- `e`: expand description
- `q`: quit

## Boundary

Personal PR review config includes only personal-safe repos. Work review is exposed only by the context-aware menu when the work Hermes profile exists on the host; work-specific data handling belongs to the work profile.

## Future Linear integration

Linear task views should also prefer off-the-shelf terminal tooling. Do not add Linear to this personal PR-review config until we have evaluated the available Linear CLI/TUI options and confirmed the correct data boundary for the current host/profile.
