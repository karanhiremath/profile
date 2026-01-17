# Repository Guidelines

## Project Structure & Module Organization
This repo is a cross-platform dev environment profile built around shell scripts and tool installers.
- Root scripts handle bootstrap and shell sourcing: `install.sh`, `myprofile.sh`, `bash_profile.sh`, `zsh_profile.sh`.
- `bin/` contains tool-specific installers/configs (`bin/<tool>/install`, `bin/<tool>/update`, configs like `bin/tmux/tmux.conf`).
- `bin/test/` hosts container-based tests and OS images (`bin/test/Dockerfile.ubuntu`, `bin/test/run-tests.sh`).
- OS- or app-specific assets live next to their installers (e.g., `bin/iterm/`, `bin/starship/`).

## Build, Test, and Development Commands
- `./install.sh`: install the profile locally.
- `make install`: wrapper for `./install.sh`.
- `just install`: same entry point if `just` is installed.
- `just <tool>` (e.g., `just tmux`, `just ghostty`): install a single component.
- `./bin/test/run-tests.sh all`: run tests across all supported OS variants.
- `./bin/test/run-tests.sh ubuntu` or `just test-ubuntu`: test a specific OS.

## Coding Style & Naming Conventions
- Shell scripts are primarily Bash; favor `set -euo pipefail` in new scripts.
- Keep installers small and focused; follow the `bin/<tool>/install` pattern.
- Use lowercase, hyphenated names for new tools or OS variants (e.g., `Dockerfile.<os>` in `bin/test/`).

## Testing Guidelines
- Tests run in Podman/Docker containers; prefer Podman for rootless runs.
- Validate specific apps with `./bin/test/validate-apps.sh git tmux vim`.
- Adding a new OS usually requires a `Dockerfile.<os>`, a `just test-<os>` target, and `bin/test/README.md` updates.

## Commit & Pull Request Guidelines
- Commit messages are short and descriptive (e.g., "fixing bug", "saving changes"). Use imperative, sentence-case phrasing when possible.
- PRs should summarize changes, list tests run (or state "not run"), and call out shell or config impacts.

## Security & Configuration Tips
- Installers modify shell/editor configs; review diffs before running them.
- Set `CONTAINER_ENGINE` to override the container runtime during tests.
