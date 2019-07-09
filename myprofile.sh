# .bash_profile
unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    CYGWIN*)    machine=Cygwin;;
    MINGW*)     machine=MinGw;;
    *)          machine="UNKNOWN:${unameOut}"
esac
if [ machine == "Darwin" ]; then
  if [ -f $(brew --prefix)/etc/bash_completion ]; then
    . $(brew --prefix)/etc/bash_completion
  fi
fi

if [ -f ~/profile/git-completion.bash ]; then
  source ~/profile/git-completion.bash
fi


function git_color {
  local git_status="$(git status 2> /dev/null)"

  if [[ ! $git_status =~ "working directory clean" ]]; then
    echo -e $(tput setaf 9)
  elif [[ $git_status =~ "Your branch is ahead of" ]]; then
    echo -e $(tput setaf 11)
  elif [[ $git_status =~ "nothing to commit" ]]; then
    echo -e $(tput setaf 12)
  else
    echo -e $(tput setaf 12)
  fi
}

function git_seperator {
  local git_status="$(git status 2> /dev/null)"
  local on_branch="On branch ([^${IFS}]*)"
  local on_commit="HEAD detached at ([^${IFS}]*)"

  if [[ $git_status =~ $on_branch ]]; then
    local branch=${BASH_REMATCH[1]}
    echo " |"
  elif [[ $git_status =~ $on_commit ]]; then
    local commit=${BASH_REMATCH[1]}
    echo " |"
  fi
}

function git_branch {
  local git_status="$(git status 2> /dev/null)"
  local on_branch="On branch ([^${IFS}]*)"
  local on_commit="HEAD detached at ([^${IFS}]*)"

  if [[ $git_status =~ $on_branch ]]; then
    local branch=${BASH_REMATCH[1]}
    echo "($branch)"
  elif [[ $git_status =~ $on_commit ]]; then
    local commit=${BASH_REMATCH[1]}
    echo "($commit)"
  fi
}

function venv_seperator {
  if [[ $VIRTUAL_ENV != "" ]]; then
      echo " |"
  fi
}

function venv {
  if [[ $VIRTUAL_ENV != "" ]]; then
    echo " (${VIRTUAL_ENV##*/})"
  fi
}

function frameworkpython {
  if [[ ! -z "$VIRTUAL_ENV" ]]; then
    PYTHONHOME=$VIRTUAL_ENV /usr/local/bin/python2.7 "$@"
  else
    /usr/bin/python2.7 "$@"
  fi
}

export PROMPT_COMMAND='PS1="\[\$(tput bold)\]\[\$(tput setaf 9)\]\T \[\$(tput setaf 11)\]| \[\$(tput setaf 12)\]\u\[\$(tput setaf 9)\]@\h \[\$(tput setaf 11)\]| \[\$(tput setaf 9)\]\w\[\$(tput setaf 11)\]\$(venv_seperator)\[\$(tput setaf 9)\]\$(venv)\[\$(tput setaf 11)\]\n\[\$(git_color)\]\$(git_branch) \[\$(tput setaf 11)\]> \[\$(tput sgr0)\]\[\$(tput bold)\]"'

export MYSQL_PS1="\R:\m:\s\ \u\ [db\ \d]\ >\ "

export MYSQL_PS1="\R:\m:\s\ \u\ [db\ \d]\ >\ "

export CLICOLOR=1"$Color_Off"
export LSCOLORS=ExFxCxDxBxEGEDABAGACAD
alias ls='ls -GFh'

alias reload='source ~/.bash_profile && echo "Bash Profile Reloaded"'
alias tmux="tmux -2"

gac () 
{ 
	git add . && git commit -m "$@";
}

gacp () 
{ 
	git add . && git commit -m "$@" && git push;
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

alias es='ssh karan@10.0.1.90'

alias npm='sudo npm'

source ~/profile/iterm2_shell_integration.bash
