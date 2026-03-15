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
        dependencies = { 'nvim-lua/plenary.nvim', 'folke/trouble.nvim' },
        config = function()
            local builtin = require('telescope.builtin')
            vim.keymap.set('n', '<leader>ff', builtin.find_files, {})
            vim.keymap.set('n', '<leader>fg', builtin.live_grep, {})
            vim.keymap.set('n', '<leader>fb', builtin.buffers, {})
            vim.keymap.set('n', '<leader>fh', builtin.help_tags, {})

            local telescope = require('telescope')

            -- Load trouble-telescope integration if available
            pcall(function() telescope.load_extension('trouble') end)

            telescope.setup {
                defaults = {
                    mappings = {},
                },
                vimgrep_arguments = {
                    'rg',
                    '--with-filename',
                    '--line-number',
                    '--column',
                    '--smart-case',
                    '--ignore-file',
                    '.gitignore',
                },
            }
        end,
    },

    {
        'folke/trouble.nvim',
        config = function()
            require("trouble").setup { icons = false }
        end,
    },

    {
        'nvim-treesitter/nvim-treesitter',
        build = ':TSUpdate',
    },

    -- use("nvim-treesitter/nvim-treesitter-context")

    {
        'theprimeagen/harpoon',
        config = function()
            local mark = require("harpoon.mark")
            local ui = require("harpoon.ui")

            vim.keymap.set("n", "<leader>a", mark.add_file)
            vim.keymap.set("n", "<C-e>", ui.toggle_quick_menu)

            vim.keymap.set("n", "<C-h>", function() ui.nav_file(1) end)
            vim.keymap.set("n", "<C-j>", function() ui.nav_file(2) end)
            vim.keymap.set("n", "<C-k>", function() ui.nav_file(3) end)
            vim.keymap.set("n", "<C-l>", function() ui.nav_file(4) end)
        end,
    },

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
        config = function()
            local lsp = require("lsp-zero")
            local cmp = require("cmp")
            local cmp_action = lsp.cmp_action()

            -- Fix Undefined global 'vim'
            -- lsp.nvim_workspace()

            lsp.on_attach(function(client, bufnr)
                local opts = { buffer = bufnr, remap = false }

                vim.keymap.set("n", "gd", function() vim.lsp.buf.definition() end, opts)
                vim.keymap.set("n", "K", function() vim.lsp.buf.hover() end, opts)
                vim.keymap.set("n", "<leader>vws", function() vim.lsp.buf.workspace_symbol() end, opts)
                vim.keymap.set("n", "<leader>vd", function() vim.diagnostic.open_float() end, opts)
                vim.keymap.set("n", "[d", function() vim.diagnostic.goto_next() end, opts)
                vim.keymap.set("n", "]d", function() vim.diagnostic.goto_prev() end, opts)
                vim.keymap.set("n", "<leader>vca", function() vim.lsp.buf.code_action() end, opts)
                vim.keymap.set("n", "<leader>vrr", function() vim.lsp.buf.references() end, opts)
                vim.keymap.set("n", "<leader>vrn", function() vim.lsp.buf.rename() end, opts)
                vim.keymap.set("i", "<C-h>", function() vim.lsp.buf.signature_help() end, opts)
            end)

            lsp.setup()
            require("mason").setup()

            require("mason-lspconfig").setup({
                ensure_installed = {
                    'snyk_ls',
                    'typos_lsp',
                    'terraformls',
                    'pylsp',
                },
                handlers = {
                    lsp.default_setup,
                    lua_ls = function()
                        local lua_opts = lsp.nvim_lua_ls()
                        require('lspconfig').lua_ls.setup(lua_opts)
                    end,
                },
            })

            -- require('luasnip.loaders.from_vscode').lazy_load()

            cmp.setup({
                sources = cmp.config.sources({
                    { name = 'path' },
                    { name = 'nvim_lsp' },
                    { name = 'luasnip' },
                }),
                window = {
                    completion = cmp.config.window.bordered(),
                    documentation = cmp.config.window.bordered(),
                },
                -- default keybindings: https://github.com/VonHeikemen/lsp-zero.nvim/blob/v3.x/README.md#keybindings-1
                mapping = cmp.mapping.preset.insert({
                    ['<Enter>'] = cmp.mapping.confirm({ select = true }),
                    ['<Tab>'] = cmp_action.tab_complete(),
                    ['<S-Tab>'] = cmp_action.select_prev_or_fallback(),
                    ['<C-Space>'] = cmp.mapping.complete(),
                    ['<C-u>'] = cmp.mapping.scroll_docs(-4),
                    ['<C-d>'] = cmp.mapping.scroll_docs(4),
                    ['<C-f>'] = cmp_action.luasnip_jump_forward(),
                    ['<C-b>'] = cmp_action.luasnip_jump_backward(),
                }),
            })
        end,
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
