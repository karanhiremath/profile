Add a new CLI tool to the profile dotfiles repo so it can be installed on any machine via `just <tool-name>`.

Tool name: $ARGUMENTS

Follow these steps exactly:

1. **Research the tool** — look up how to install `$ARGUMENTS` on macOS (via Homebrew) and Linux (via apt, dnf, or GitHub releases as fallback). Check if there's an official tap or package name.

2. **Create the install script** at `bin/$ARGUMENTS/install` following the established pattern in this repo. Use existing scripts like `bin/k9s/install` or `bin/stern/install` as reference. The script must:
   - Start with `#!/bin/bash` and `set -euo pipefail` + `shopt -s failglob`
   - Auto-detect `PROFILE_DIR` and `APP_BIN` if not set
   - Source `"${APP_BIN}/sh/shell_fns"` and `"${APP_BIN}/sh/brew_helper.sh"`
   - Check if already installed with `command -v`
   - Handle Darwin (brew) and Linux (apt/dnf/GitHub release fallback) cases
   - Use `install_messages` for start/end logging
   - Be executable (`chmod +x`)

3. **Add a just recipe** to the `Justfile`. Place it alphabetically or in the appropriate section. The recipe must have:
   - A doc-comment ABOVE the recipe name (not inside the body)
   - `#!/usr/bin/env bash` as the FIRST line of the recipe body
   - `set -euo pipefail`, export `PROFILE_DIR` and `APP_BIN`, then call `./bin/$ARGUMENTS/install`

4. **Update `README.md`** — add the tool to the appropriate table (AI Toolkit, Kubernetes Toolkit, Infrastructure, Shell & Editor, or macOS). If it doesn't fit an existing category, add it to Infrastructure.

5. **If the tool belongs to a toolkit group** (ai-toolkit or k8s-toolkit), also add an entry to the corresponding `bin/<toolkit>/install-all` script following the existing pattern with the `failed_installs` array.

6. **Verify** by running `just --dry-run $ARGUMENTS` to confirm the recipe is valid.
