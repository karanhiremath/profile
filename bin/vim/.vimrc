
set autoread
" ---- Minimal configuration:
set smartindent   " Do smart autoindenting when starting a new line
set shiftwidth=4  " Set number of spaces per auto indentation
set expandtab     " When using <Tab>, put spaces instead of a <tab> character

set ai "Auto indent
set si "Smart indent
set wrap "Wrap lines

syntax on

filetype plugin indent on

set guicursor=n-v-c:block-Cursor
set guicursor+=i:ver100-iCursor
set guicursor+=n-v-c:blinkon0

let mapleader = ','

" Edit the vimrc file
nnoremap ev  :e $MYVIMRC<CR>
nnoremap <leader>evr :source  $MYVIMRC<CR>
nnoremap tt  :tablast<CR>
nnoremap te  :tabedit<Space>
nnoremap tn  :tabnext<CR>
nnoremap tp  :tabprev<CR>
nnoremap tc  :tabnew<CR>
nnoremap tm  :tabm<Space>
nnoremap tx  :tabclose<CR>
nnoremap t1  1gt<CR>
nnoremap t2  2gt<CR>
nnoremap t3  3gt<CR>
nnoremap t4  4gt<CR>
nnoremap t5  5gt<CR>
nnoremap t6  6gt<CR>
nnoremap fbk :bd!<CR>
nnoremap fak :%bd!<bar>e#<CR>
nnoremap <leader>bo  :bp<CR>
nnoremap <leader>bi  :bn<CR>

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
