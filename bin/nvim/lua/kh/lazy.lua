-- lazy.nvim plugin manager setup
-- To activate: change require("kh.packer") to require("kh.lazy") in lua/kh/init.lua

local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
    vim.fn.system({
        "git",
        "clone",
        "--filter=blob:none",
        "https://github.com/folke/lazy.nvim.git",
        "--branch=stable",
        lazypath,
    })
end
vim.opt.rtp:prepend(lazypath)

-- Use older nvim-lspconfig commit on nvim 0.9.x (marker file set by install script)
local use_old_lspconfig = vim.fn.filereadable(vim.fn.expand('~/.config/nvim/.use-old-lspconfig')) == 1

require("lazy").setup({

    {
        'nvim-telescope/telescope.nvim',
        branch = 'master',
        dependencies = { 'nvim-lua/plenary.nvim' },
    },

    {
        'folke/trouble.nvim',
        config = function()
            require("trouble").setup { icons = false }
        end,
    },

    {
        'nvim-treesitter/nvim-treesitter',
        build = function()
            local ts_update = require('nvim-treesitter.install').update({ with_sync = true })
            ts_update()
        end,
    },

    -- use("nvim-treesitter/nvim-treesitter-context")

    'theprimeagen/harpoon',
    'theprimeagen/refactoring.nvim',
    'mbbill/undotree',
    'tpope/vim-fugitive',

    {
        'VonHeikemen/lsp-zero.nvim',
        branch = 'v3.x',
        dependencies = {
            -- LSP Support - use older commit for nvim 0.9.x if needed
            use_old_lspconfig
                and { 'neovim/nvim-lspconfig', commit = 'a981d4447b92c54a4d464eb1a76b799bc3f9a771' }
                or  'neovim/nvim-lspconfig',
            'williamboman/mason.nvim',
            'williamboman/mason-lspconfig.nvim',

            -- linter
            'mfussenegger/nvim-lint',
            'rshkarin/mason-nvim-lint',

            -- Autocompletion
            'hrsh7th/nvim-cmp',
            'hrsh7th/cmp-buffer',
            'hrsh7th/cmp-path',
            'hrsh7th/cmp-cmdline',
            'saadparwaiz1/cmp_luasnip',
            'hrsh7th/cmp-nvim-lsp',
            'hrsh7th/cmp-nvim-lua',

            -- Snippets
            'L3MON4D3/LuaSnip',
            'rafamadriz/friendly-snippets',
        },
    },

    'github/copilot.vim',

    'nvim-lua/plenary.nvim',

    {
        'Al0den/notion.nvim',
        dependencies = { 'nvim-telescope/telescope.nvim', 'nvim-lua/plenary.nvim' },
        config = function()
            require("notion").setup()
        end,
    },

})
