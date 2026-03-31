export MYSQL_PS1="\R:\m:\s\ \u\ [db\ \d]\ >\ "
export EDITOR=nvim
export VISUAL=nvim

alias ls='ls -GFh'

alias tmux="tmux -2"


function gb ()
{
    git checkout -b "$1"
}
function gac ()
{
	git add "$1" && git commit -m "$2";
}

function gacp ()
{
	git add "$1" && git commit -m "$2" && git push;
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
    tmux has-session -t "${sessionname}" && tmux attach-session -t "${sessionname}" || exec tmux new -s "${sessionname}"
}
function mac ()
{
    local sessionname="${1:-mac}"
    echo "Connecting to local session name: ${sessionname}"
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

# use bob
alias nvim="~/.local/share/bob/nvim-bin/nvim"

# tmux session management
function tl() { "${PROFILE_DIR:-$HOME/profile}"/bin/tmux/tmux-load "$@"; }
function ts() { "${PROFILE_DIR:-$HOME/profile}"/bin/tmux/tmux-save "$@"; }
function tc() { "${PROFILE_DIR:-$HOME/profile}"/bin/tmux/tmux-connect "$@"; }

# tc completions — dynamically reads host registry
_tc_completions() {
    local registry="${PROFILE_DIR:-$HOME/profile}/bin/tmux/hosts/registry.conf"
    local -a hosts flags
    flags=("--list" "--status" "--help")
    if [[ -f "$registry" ]]; then
        hosts=(${(f)"$(grep -v '^#' "$registry" | grep -v '^$' | cut -d'|' -f1)"})
    fi
    if (( CURRENT == 2 )); then
        _describe 'host' hosts -- flags
    elif (( CURRENT == 3 )); then
        # Second arg: session name — complete from local tmux sessions or common names
        local -a sessions=("dev" "mac" "gpu" "work" "fips" "ops" "home")
        _describe 'session' sessions
    fi
}
compdef _tc_completions tc

# ── Cluster shortcuts ──────────────────────────────────────────
# Training cluster:  tc (crusoe default), tc tg (together)
# Inference cluster: ic (together default), ic us, ic eu, ic uk, ic ap, ic au
#
# These wrap `tc` (tmux-connect). No args = default landing pad.

function train() {
    case "${1:-}" in
        tg|together)  tc tg-train "${2:-}" ;;
        "")           tc cxis-devlarge "${2:-}" ;;
        *)            tc "$@" ;;  # passthrough to tmux-connect
    esac
}

function ic() {
    case "${1:-}" in
        tg|"")        tc ic-tg-prod "${2:-}" ;;
        staging)      tc ic-tg-staging "${2:-}" ;;
        us)           tc ic-us "${2:-}" ;;
        eu)           tc ic-eu "${2:-}" ;;
        uk)           tc ic-uk "${2:-}" ;;
        ap)           tc ic-ap "${2:-}" ;;
        au)           tc ic-au "${2:-}" ;;
        *)            echo "ic: unknown region '$1' (tg|us|eu|uk|ap|au)" ;;
    esac
}

_train_completions() {
    if (( CURRENT == 2 )); then
        local -a clusters=("tg" "together")
        _describe 'cluster' clusters
    elif (( CURRENT == 3 )); then
        local -a sessions=("dev" "fips" "ops" "home")
        _describe 'session' sessions
    fi
}

_ic_completions() {
    if (( CURRENT == 2 )); then
        local -a regions=("tg" "staging" "us" "eu" "uk" "ap" "au")
        _describe 'region' regions
    elif (( CURRENT == 3 )); then
        local -a sessions=("ops" "dev" "home")
        _describe 'session' sessions
    fi
}

compdef _train_completions train
compdef _ic_completions ic
