#!/bin/bash

set -euo pipefail

shopt -s failglob

medir=$( pwd "$0" )
export PROFILE_DIR="${medir}"

. $PROFILE_DIR/bin/sh/shell_fns --source-only

generate_config_vars

echo "${MACHINE} ${ARCH}"

# install cargo and then just so we can use Justfile to do the rest
install_app "cargo"
install_app "just"

just all

if [[ $machine == "Mac" ]]; then
    just mac
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

if [[ ! -e ~/.zshrc ]]; then
    # Setup Oh My ZSH and any plugins:
#    git clone https://github.com/ohmyzsh/ohmyzsh.git ~/.dotfiles/.oh-my-zsh
#    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
#    git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
    echo "No oh-my-zsh"
else
    echo "ZSH Profile found at ~/.zshrc"
fi

# add brew to `/.zshrc
if [[ $machine == "Mac" ]]; then
    if grep -q "/opt/homebrew/bin" ~/.zshrc; then
        echo "homebrew bin added to ~/.zshrc"
    else
        echo "adding brew to ~/.zshrc PATH"
        echo "export PATH=/opt/homebrew/bin:$PATH" >> ~/.zshrc
    fi
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

# NVIM
curl -fLo "${XDG_DATA_HOME:-$HOME/.local/share}"/nvim/site/autoload/plug.vim --create-dirs \
   https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim

ln -si "$medir/vimprofile.sh" ~/.vimrc
if [[ ! -e ~/.config/nvim ]]; then
    mkdir -p ~/.config/nvim
fi
ln -si "$medir/vimprofile.sh" ~/.config/nvim/init.vim
echo "Symlinking $medir/vimprofile.sh in ~/.vimrc"

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

just nvim
