# gh-dash PR review

Terminal-native GitHub PR review using the off-the-shelf [`dlvhdr/gh-dash`](https://github.com/dlvhdr/gh-dash) GitHub CLI extension.

## Install

```bash
gh extension install dlvhdr/gh-dash
```

If already installed, upgrade with:

```bash
gh extension upgrade gh-dash
```

## Launch

From any terminal:

```bash
gh dash --config ~/src/profile/bin/gh/gh-dash/config.yml
```

From tmux after installing/reloading `bin/tmux/tmux.conf`:

- `prefix P` opens the dashboard in a horizontal pane
- `prefix C-p` opens the dashboard in a full tmux window named `pr-review`

The profile tmux prefix is `C-a`, so the common shortcuts are:

```text
C-a P
C-a C-p
```

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

This is intentionally an off-the-shelf GitHub TUI plus config. Do not grow a bespoke PR dashboard unless `gh-dash` and stock `gh` cannot support the workflow.
