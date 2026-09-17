export MYSQL_PS1="\R:\m:\s\ \u\ [db\ \d]\ >\ "
export EDITOR="$HOME/.local/share/bob/nvim-bin/nvim"
export VISUAL="$HOME/.local/share/bob/nvim-bin/nvim"

alias ls='ls -GFh'

alias tmux="tmux -2"


function gb ()
{
    git checkout -b "$1"
}

# gac — git add + commit
# Usage:
#   gac "message"              add all + commit
#   gac file "message"         add file + commit
#   gac file1 file2 "message"  add files + commit (last arg is message)
function gac ()
{
    if [[ $# -eq 0 ]]; then
        echo "Usage: gac [files...] \"message\""
        echo "       gac \"message\"            (adds all changed files)"
        return 1
    fi

    if [[ $# -eq 1 ]]; then
        git add -A && git commit -m "$1"
    else
        local msg="${@[-1]}"
        local files=("${@[1,-2]}")
        git add "${files[@]}" && git commit -m "$msg"
    fi
}

# gacp — git add + commit + push
# Same args as gac, but pushes after commit
function gacp ()
{
    if [[ $# -eq 0 ]]; then
        echo "Usage: gacp [files...] \"message\""
        echo "       gacp \"message\"            (adds all, commits, pushes)"
        return 1
    fi

    gac "$@" && git push
}

# gacpv — git add + commit + push + vendor to hosts
# Commits, pushes, then pulls on remote hosts via tc/ssh
# Usage:
#   gacpv "message"                           push + pull on all registered hosts
#   gacpv "message" --hosts mini,cxis-dev     push + pull on specific hosts
function gacpv ()
{
    if [[ $# -eq 0 ]]; then
        echo "Usage: gacpv [files...] \"message\" [--hosts host1,host2]"
        return 1
    fi

    # Parse --hosts flag from the end
    local hosts_csv=""
    local args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --hosts) hosts_csv="$2"; shift 2 ;;
            *)       args+=("$1"); shift ;;
        esac
    done

    # Commit and push
    gacp "${args[@]}" || return 1

    # Determine repo name for remote pull path
    local repo_name
    repo_name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)")
    local remote_dir="~/src/${repo_name}"

    # Default vendor hosts (override with PC_VENDOR_HOSTS env var)
    local default_hosts="${PC_VENDOR_HOSTS:-}"
    local host_list="${hosts_csv:-$default_hosts}"

    if [[ -z "$host_list" ]]; then
        echo "\n${_green}Pushed.${_reset} No vendor hosts configured."
        echo "  Set PC_VENDOR_HOSTS=\"mini,cxis-dev\" or use --hosts"
        return 0
    fi

    echo "\n${_bold}Vendoring to hosts...${_reset}"
    local IFS=','
    for host in $host_list; do
        host=$(echo "$host" | tr -d ' ')
        printf "  %-20s " "$host"
        if ssh -o ConnectTimeout=5 "$host" "cd ${remote_dir} 2>/dev/null && git pull --ff-only" 2>/dev/null; then
            echo "${_green}✓${_reset}"
        else
            echo "${_red}✗${_reset} (unreachable or pull failed)"
        fi
    done
}

function gd ()
{
    git add "$1" && git commit -m "$2" && arc diff;
}

function gs ()
{
    git status
}

function docker-c-start ()
{
  docker-compose -f "$@" build && docker-compose -f "$@" up;
}

function activate ()
{
  if [ -z "$1" ]
    then
      echo "No virtualenv supplied"
  else
    source "$@/bin/activate"
  fi
}

alias fileserver="ssh karan@karanhiremath.com -t -- /bin/sh -c 'exec tmux has-session -t fs && tmux attach-session -t fs || exec tmux new -s fs'"

function local_tmux ()
{
    local sessionname="${1:-local}"
    echo "Connecting to local session name: ${sessionname}"
    tmux has-session -t "=${sessionname}" && tmux attach-session -t "=${sessionname}" || exec tmux new -s "${sessionname}"
}
function hermes_sandbox_env ()
{
    local sandbox_env="${PROFILE_DIR:-${HOME}/src/profile}/bin/hermes/sandbox-env.sh"
    if [ -r "${sandbox_env}" ]; then
        # shellcheck source=/dev/null
        source "${sandbox_env}"
    else
        echo "warning: Hermes sandbox env not found: ${sandbox_env}" >&2
    fi
}

# hs — Hermes sandbox entrypoint.
# Usage: hs [project-or-path], hs --shell [project], hs --container-shell [project]
function hs ()
{
    local hs_bin="${PROFILE_DIR:-${HOME}/src/profile}/bin/hermes/hs"
    if [ ! -x "${hs_bin}" ]; then
        echo "hs: entrypoint not executable: ${hs_bin}" >&2
        return 1
    fi
    "${hs_bin}" "$@"
}

function mac ()
{
    local sessionname="${1:-mac}"
    hermes_sandbox_env

    if [ "${1:-}" = "status" ]; then
        local target_session="${2:-mac}"
        local tmux_status="missing"
        local herdr_status="missing"
        if command -v tmux >/dev/null 2>&1; then
            if tmux has-session -t "=${target_session}" 2>/dev/null; then
                tmux_status="exists"
            else
                tmux_status="not-running"
            fi
        fi
        if command -v herdr >/dev/null 2>&1; then
            herdr_status="available: $(command -v herdr)"
        fi
        cat <<EOF
mac_status:
  session: ${target_session}
  tmux_session: ${tmux_status}
  herdr: ${herdr_status}
  HERMES_SANDBOX_PROFILE: ${HERMES_SANDBOX_PROFILE:-herm-sandbox}
  HERMES_HOME: ${HERMES_HOME:-${HOME}/.hermes/profiles/${HERMES_SANDBOX_PROFILE:-herm-sandbox}}
  HERMES_PROFILE: ${HERMES_PROFILE:-${HERMES_SANDBOX_PROFILE:-herm-sandbox}}
  HERMES_TOOLCHAIN: ${HERMES_TOOLCHAIN:-${HOME}/.local/share/hermes-toolchain}
  TERMINAL_ENV: ${TERMINAL_ENV:-unset}
  TERMINAL_DOCKER_EXTRA_ARGS: ${TERMINAL_DOCKER_EXTRA_ARGS:-unset}
  DOCKER_HOST: ${DOCKER_HOST:-unset}
  gateway_identity: unset
  mobile_boundary: disabled-or-unset
EOF
        return 0
    fi

    if command -v tmux >/dev/null 2>&1; then
        tmux set-environment -g HERMES_SANDBOX_PROFILE "${HERMES_SANDBOX_PROFILE:-herm-sandbox}" 2>/dev/null || true
        tmux set-environment -g HERMES_HOME "${HERMES_HOME:-${HOME}/.hermes/profiles/${HERMES_SANDBOX_PROFILE:-herm-sandbox}}" 2>/dev/null || true
        tmux set-environment -g HERMES_PROFILE "${HERMES_PROFILE:-${HERMES_SANDBOX_PROFILE:-herm-sandbox}}" 2>/dev/null || true
        tmux set-environment -g HERMES_TOOLCHAIN "${HERMES_TOOLCHAIN:-${HOME}/.local/share/hermes-toolchain}" 2>/dev/null || true
        tmux set-environment -g TERMINAL_ENV "${TERMINAL_ENV:-docker}" 2>/dev/null || true
        tmux set-environment -g TERMINAL_DOCKER_EXTRA_ARGS "${TERMINAL_DOCKER_EXTRA_ARGS:-}" 2>/dev/null || true
        tmux set-environment -g DOCKER_HOST "${DOCKER_HOST:-}" 2>/dev/null || true
    fi
    echo "Connecting to local session name: ${sessionname} (Hermes sandbox: ${HERMES_HOME})"
    local_tmux "${sessionname}"
}

alias reload-ssh='eval $(tmux show-env -s | grep '^SSH_')'

alias cl='clear'

# export FZF_TMUX=1

# Using highlight (http://www.andre-simon.de/doku/highlight/en/highlight.html)
# export FZF_CTRL_T_OPTS="--preview '(highlight -O ansi -l {} 2> /dev/null || cat {} || tree -C {}) 2> /dev/null | head -200'"

# bind "$(bind -s | grep '^"\\C-r"' | sed 's/"/"\\C-x/' | sed 's/"$/\\C-m"/')"

# Search a file with fzf inside a Tmux pane and then open it in an editor

function fvi ()
{
    vi "$(fzf-tmux)"
}

function profile ()
{
    cd ~/profile
}

alias vi="nvim"

# update pi coding agent
alias pi-update="${PROFILE_DIR}/bin/pi/install"

# use bob
alias nvim="~/.local/share/bob/nvim-bin/nvim"

# pi-code session manager (tmux + nvim + pi)
# Binary built from profile/bin/pc (Rust). Install: just pc
function pc() { "$HOME/.local/bin/pc" "$@"; }

# kh — pi agent fleet launcher
# Wraps pc with sane defaults. Inside nvim, use <C-h> prefix for fleet nav.
# Usage: kh [project] [-- pi-args...]   e.g. kh bifrost -- -c
function kh() {
  if [[ $# -eq 0 ]]; then
    pc
  else
    pc "$@"
  fi
}

# pc completions — projects, subcommands, pi flags
_pc_completions() {
    local src_dir="${PC_SRC_DIR:-$HOME/src}"
    local saves_dir="${PC_SAVES_DIR:-$HOME/.config/pc/sessions}"
    local -a projects flags subcmds
    subcmds=("save:save current session layout" "load:load a saved session layout")
    flags=("--status:list active sessions" "--kill:kill a session" "--list:machine-readable list" "--help:show help")
    if [[ -d "$src_dir" ]]; then
        projects=(${(f)"$(find "$src_dir" -maxdepth 1 -mindepth 1 -type d -exec basename {} \; | sort)"})
    fi
    if (( CURRENT == 2 )); then
        _describe 'subcommand' subcmds -- flags
        _describe 'project' projects
    elif (( CURRENT == 3 )); then
        case "${words[2]}" in
            save)
                # complete with active sessions
                local -a active
                active=(${(f)"$(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^pi_' | sed 's/^pi_//')"})
                _describe 'session' active
                ;;
            load)
                # complete with saved sessions
                local -a saves
                if [[ -d "$saves_dir" ]]; then
                    saves=(${(f)"$(ls "$saves_dir"/*.json 2>/dev/null | xargs -I{} basename {} .json | sort)"})
                fi
                _describe 'saved-session' saves
                ;;
            *)
                local -a sep=("--")
                _describe 'separator' sep
                ;;
        esac
    elif (( CURRENT >= 4 )); then
        local -a pi_flags=("-c" "-r" "--model" "--continue" "--resume" "--no-session")
        _describe 'pi-flag' pi_flags
    fi
}
compdef _pc_completions pc

# Source work-specific extensions if present
# karan.hiremath provides: tc (training clusters), ic (inference clusters), dashboard
[ -f "$HOME/src/karan.hiremath/scripts/shell-ext.sh" ] && source "$HOME/src/karan.hiremath/scripts/shell-ext.sh"
