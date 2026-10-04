#!/usr/bin/env just --justfile
# fleet.just — lane operations for the agentic OS.
# Import from the main Justfile:  import? 'fleet.just'
# Every recipe is zsh. Two sessions per lane: cos-<lane> plans, <lane> works.

FLEET := "$(pwd)/bin/fleet/fleet"

# Bring up coordination + workflow sessions for the ao lanes
fleet-up *LANES:
    #!/usr/bin/env zsh
    set -uo pipefail
    {{FLEET}} up {{LANES}}

# Bring up the infra family
fleet-up-infra:
    #!/usr/bin/env zsh
    set -uo pipefail
    {{FLEET}} up --infra

# List every lane pane as tsv: session, window, command, pane-id
fleet-ls:
    #!/usr/bin/env zsh
    set -uo pipefail
    {{FLEET}} ls

# Attach the WORKFLOW session for a lane:  just fleet-work ao2
fleet-work LANE:
    #!/usr/bin/env zsh
    exec {{FLEET}} attach {{LANE}}

# Attach the COORDINATION session for a lane:  just fleet-plan ao2
fleet-plan LANE:
    #!/usr/bin/env zsh
    exec {{FLEET}} plan {{LANE}}

# Send a line to a lane window:  just fleet-steer ao2:do "read the spec and go"
fleet-steer TARGET MSG:
    #!/usr/bin/env zsh
    set -uo pipefail
    {{FLEET}} steer {{TARGET}} {{MSG}}

# Dispatch a pi worker at a spec FILE (never an inline string)
fleet-dispatch TARGET SPEC:
    #!/usr/bin/env zsh
    set -uo pipefail
    [[ -r {{SPEC}} ]] || { print -u2 "fleet-dispatch: unreadable spec: {{SPEC}}"; exit 1 }
    {{FLEET}} steer {{TARGET}} "Read {{SPEC}} and execute it"

# Tear down both sessions for a lane
fleet-down LANE:
    #!/usr/bin/env zsh
    {{FLEET}} down {{LANE}}

# Check a lane's live pane commands and context use
fleet-status LANE:
    #!/usr/bin/env zsh
    set -uo pipefail
    {{FLEET}} ls | grep -E "^(cos-)?{{LANE}}\b"

# Create a worktree for lane work on a TRUSTED repo, then report its path
fleet-worktree REPO BRANCH:
    #!/usr/bin/env zsh
    set -uo pipefail
    cd {{REPO}}
    origin=$(git remote get-url origin)
    [[ $origin == *karanhiremath/* ]] || { print -u2 "refusing: origin is not karanhiremath/*: $origin"; exit 1 }
    git fetch origin --prune
    wt="${PWD}-wt-{{BRANCH}}"
    git worktree add "$wt" -b {{BRANCH}} 2>/dev/null || git worktree add "$wt" {{BRANCH}}
    print -r -- "$wt"
