syntax on

filetype plugin on
filetype indent on

set autoread

set tabstop=4
set softtabstop=4
set shiftwidth=4

set number relativenumber
:augroup numbertoggle
:  autocmd!
:  autocmd BufEnter,FocusGained,InsertLeave * set relativenumber
:  autocmd BufLeave,FocusLost,InsertEnter   * set norelativenumber
:augroup END

set expandtab
set laststatus=2

set wildmenu
set ruler
set cmdheight=2

set backspace=eol,start,indent
set whichwrap+=<,>,h,l

set ignorecase

set smartcase

set hlsearch
set incsearch

set magic

set showmatch

set noswapfile
set nobackup
set undodir=~/.vim/undodir
set undofile

set ai "Auto indent
set si "Smart indent
set wrap "Wrap lines

" ---- Minimal configuration:
set smartindent   " Do smart autoindenting when starting a new line
set shiftwidth=4  " Set number of spaces per auto indentation
set expandtab     " When using <Tab>, put spaces instead of a <tab> character

" ---- Good to have for consistency
" set tabstop=4   " Number of spaces that a <Tab> in the file counts for
" set smarttab    " At <Tab> at beginning line inserts spaces set in shiftwidth

" ---- Bonus for proving the setting
" Displays '-' for trailing space, '>-' for tabs and '_' for non breakable space
set listchars=tab:>-,trail:-,nbsp:_
set list

nnoremap <esc> :noh<return><esc>
nnoremap <esc>^[ <esc>^[

" Return to last edit position when opening files (You want this!)
autocmd BufReadPost *
     \ if line("'\"") > 0 && line("'\"") <= line("$") |
     \   exe "normal! g`\"" |
     \ endif
" Remember info about open buffers on close
set viminfo^=%



vnoremap <silent> # :s/^/#/<cr>:noh<cr>
vnoremap <silent> -# :s/^#//<cr>:noh<cr>

let data_dir = has('nvim') ? stdpath('data') . '/site' : '~/.vim'
if empty(glob(data_dir . '/autoload/plug.vim'))
  silent execute '!curl -fLo '.data_dir.'/autoload/plug.vim --create-dirs  https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim'
  autocmd VimEnter * PlugInstall --sync | source $MYVIMRC
endif

call plug#begin(has('nvim') ? stdpath('data') . '/plugged' : '~/.vim/plugged')
    Plug 'vmchale/just-vim'
    Plug 'tpope/vim-sensible'
    Plug 'raghur/vim-ghost', {'do': ':GhostInstall'}
    Plug 'hashivim/vim-terraform'
    Plug 'tmux-plugins/vim-tmux-focus-events'
    Plug 'sheerun/vim-polyglot'
call plug#end()

nmap <leader>gd <Plug>(coc-definition)
nmap <leader>gr <Plug>(coc-references)
nnoremap <C-p> :GFiles<CR>

set laststatus=2
set viminfo='20,<1000,s1000
