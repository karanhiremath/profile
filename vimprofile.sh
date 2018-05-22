syntax on

filetype plugin on
filetype indent on

set autoread

set tabstop=2
set softtabstop=2
set shiftwidth=2

set number
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

set ai "Auto indent
set si "Smart indent
set wrap "Wrap lines

" Return to last edit position when opening files (You want this!)
autocmd BufReadPost *
     \ if line("'\"") > 0 && line("'\"") <= line("$") |
     \   exe "normal! g`\"" |
     \ endif
" Remember info about open buffers on close
set viminfo^=%

set laststatus=2

