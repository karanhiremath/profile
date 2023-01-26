#!/bin/bash

set -e
set -u

medir=$( pwd "$0" )

unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    CYGWIN*)    machine=Cygwin;;
    MINGW*)     machine=MinGw;;
    *)          machine="UNKNOWN:${unameOut}"
esac

if [ $machine == "Mac" ]; then
    echo "Pulling latest iterm2_shell_integration.zsh and iterm2_shell_integration.bash"
    curl -l https://iterm2.com/shell_integration/zsh \
        -o ./.iterm2_shell_integration.zsh
    curl -l https://iterm2.com/shell_integration/bash \
        -o ./.iterm2_shell_integration.bash
    which -s brew
    if [[ $? != 0 ]] ; then
        # install Homebrew
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        echo "Running brew update..."
        brew update
    fi
fi

if [[ ! -e ~/.bash_profile ]]; then
    touch ~/.bash_profile
else
    echo "Bash Profile found at ~/.bash_profile"
fi

if grep -q "$medir/bash_profile.sh" ~/.bash_profile; then
    echo "bash_profile.sh already sourced in ~/.bash_profile"
else
    echo "Sourcing $medir/bash_profile.sh in ~/.bash_profile"
    echo "source $medir/bash_profile.sh" >> ~/.bash_profile
fi

if grep -q "$medir/myprofile.sh" ~/.bash_profile; then
    echo "myprofile.sh already sourced in ~/.bash_profile"
else
    echo "Sourcing $medir/myprofile.sh in ~/.bash_profile"
    echo "source $medir/myprofile.sh" >> ~/.bash_profile
fi

if [[ ! -e ~/.bash_profile ]]; then
    touch ~/.bash_profile
else
    echo "Bash Profile found at ~/.bash_profile"
fi

# confirm .zprofile and .zshrc are setup appropriately
if grep -q "$medir/zsh_profile.sh" ~/.zshrc; then
    echo "zsh_profile.sh already sourced in ~/.zshrc"
else
    echo "Sourcing $medir/zsh_profile.sh in ~/.zshrc"
    echo "source $medir/zsh_profile.sh" >> ~/.zshrc
fi

if grep -q "$medir/myprofile.sh" ~/.zshrc; then
    echo "myprofile.sh already sourced in ~/.zshrc"
else
    echo "Sourcing $medir/myprofile.sh in ~/.zshrc"
    echo "source $medir/myprofile.sh" >> ~/.zshrc
fi

if [[ ! -e ~/.vimrc ]]; then
    touch ~/.vimrc
else
    echo "vimrc found at ~/.vimrc"
fi

if grep -q "$medir/vimprofile.sh" ~/.vimrc; then
    echo "vimprofile.sh already sourced in ~/.vimrc"
else
    echo "Sourcing $medir/vimprofile.sh in ~/.vimrc"
    echo "source $medir/vimprofile.sh" >> ~/.vimrc


fi

if [[ ! -e ~/.vim/undodir ]]; then
    # if ~/.vim/undodir not present, create ~/.vim/undodir
    mkdir -p ~/.vim/undodir
else
    echo "~/.vim/undodir already exists"
fi

if [[ ! -e ~/.vim/autoload/plug.vim ]]; then
    # install plug.vim
    curl -fLo ~/.vim/autoload/plug.vim --create-dirs \
        https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
else
    echo "~/.vim/autoload/plug.vim already exists"
fi

if [[ ! -e ~/.tmux.conf ]]; then
    touch ~/.tmux.conf
else
    echo "tmux config found at ~/.tmux.conf"
fi

if grep -q "$medir/.tmux.conf" ~/.tmux.conf; then
    echo ".tmux.conf already sourced in ~/.tmux.conf"
else
    echo "Sourcing $medir/.tmux.conf in ~/.tmux.conf"
    echo "source-file $medir/.tmux.conf" >> ~/.tmux.conf
fi

if [[ ! -e ~/.tmux/plugins/tpm/ ]]; then
  git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
else
    echo "~/.tmux/plugins/tmp exists!" 
fi
