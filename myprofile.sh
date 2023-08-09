
export MYSQL_PS1="\R:\m:\s\ \u\ [db\ \d]\ >\ "

alias ls='ls -GFh'

alias tmux="tmux -2"

git config --global user.email 'me@karanhiremath.com'
git config --global user.name 'Karan Hiremath'
git config --global --add --bool push.autoSetupRemote true
git config --global pull.rebase true

gac () 
{ 
	git add "$1" && git commit -m "$2";
}

gacp () 
{ 
	git add "$1" && git commit -m "$2" && git push;
}

gd ()
{
    git add "$1" && git commit -m "$2" && arc diff;
}

gs ()
{
    git status
}

docker-c-start ()
{
  docker-compose -f "$@" build && docker-compose -f "$@" up;
}

activate ()
{
  if [ -z "$1" ] 
    then
      echo "No virtualenv supplied"
  else
    source "$@/bin/activate"
  fi
}

alias fileserver="ssh karan@karanhiremath.com -t -- /bin/sh -c 'exec tmux has-session -t fs && tmux attach-session -t fs || exec tmux new -s fs'"

alias mac="tmux has-session -t mac && tmux attach-session -t mac || exec tmux new -s mac"

alias reload-ssh='eval $(tmux show-env -s | grep '^SSH_')'

alias cl='clear'

# export FZF_TMUX=1

# Using highlight (http://www.andre-simon.de/doku/highlight/en/highlight.html)
# export FZF_CTRL_T_OPTS="--preview '(highlight -O ansi -l {} 2> /dev/null || cat {} || tree -C {}) 2> /dev/null | head -200'"

# bind "$(bind -s | grep '^"\\C-r"' | sed 's/"/"\\C-x/' | sed 's/"$/\\C-m"/')"

# Search a file with fzf inside a Tmux pane and then open it in an editor

fvi ()
{
    vi "$(fzf-tmux)"
}
