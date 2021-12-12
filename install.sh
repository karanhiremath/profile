#!/bin/bash

set -e
set -u

medir=$( pwd "$0" )

if [[ ! -e ~/.bash_profile ]]; then
    touch ~/.bash_profile
else
    echo "Bash Profile found at ~/.bash_profile"
fi

if grep -q "$medir/myprofile.sh" ~/.bash_profile; then
    echo "myprofile.sh already sourced in ~/.bash_profile"
else
    echo "Sourcing $medir/myprofile.sh in ~/.bash_profile"
    echo "source $medir/myprofile.sh" >> ~/.bash_profile
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

