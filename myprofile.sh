export MYSQL_PS1="\R:\m:\s\ \u\ [db\ \d]\ >\ "

alias ls='ls -GFh'

alias tmux="tmux -2"

git config --global user.name 'Karan Hiremath'
git config --global --add --bool push.autoSetupRemote true
git config --global pull.rebase true


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
