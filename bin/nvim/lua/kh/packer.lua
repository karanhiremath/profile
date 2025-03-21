-- This fie can be loaded by calling `lua require('plugins')` from your init.vim
local fn = vim.fn

-- Automatically install packer
local ensure_packer = function()
  local fn = vim.fn
  local install_path = fn.stdpath('data')..'/site/pack/packer/start/packer.nvim'
  if fn.empty(fn.glob(install_path)) > 0 then
    fn.system({'git', 'clone', '--depth', '1', 'https://github.com/wbthomason/packer.nvim', install_path})
    vim.cmd [[packadd packer.nvim]]
    return true
  end
  return false
end

-- Autocommand that reloads neovim whenever you save the plugins.lua file
vim.cmd([[
  augroup packer_user_config
    autocmd!
    autocmd BufWritePost plugins.lua source <afile> | PackerSync
  augroup end
]])

-- Use a protected call so we don't error out on first use
local status_ok, packer = pcall(require, "packer")
if not status_ok then
	return
end

local packer_bootstrap = ensure_packer()

-- Have packer use a popup window
packer.init({
	display = {
		open_fn = function()
			return require("packer.util").float({ border = "rounded" })
		end,
	},
})

return require('packer').startup(function(use)
	use 'wbthomason/packer.nvim'

    use {
      'nvim-telescope/telescope.nvim', tag = '0.1.5',
      requires = { {'nvim-lua/plenary.nvim'} }
    }

    use {
        "folke/trouble.nvim",
        config = function()
            require("trouble").setup {
                icons = false,
                -- your configuration comes here
                -- or leave it empty to use the default settings
                -- refer to the configuration section below
            }
      end
    }

    use {
        'nvim-treesitter/nvim-treesitter',
        run = function()
            local ts_update = require('nvim-treesitter.install').update({ with_sync = true })
            ts_update()
        end
    }
    use("nvim-treesitter/playground")
    use("theprimeagen/harpoon")
    use("theprimeagen/refactoring.nvim")
    use("mbbill/undotree")
    use("tpope/vim-fugitive")
    -- use("nvim-treesitter/nvim-treesitter-context")

    use {
      'VonHeikemen/lsp-zero.nvim',
      branch = 'v3.x',
      requires = {
          -- LSP Support
          {'neovim/nvim-lspconfig'},
          {'williamboman/mason.nvim'},
          {'williamboman/mason-lspconfig.nvim'},

          -- linter
          {'mfussenegger/nvim-lint'},
          {'rshkarin/mason-nvim-lint'},


          -- Autocompletion
          {'hrsh7th/nvim-cmp'},
          {'hrsh7th/cmp-buffer'},
          {'hrsh7th/cmp-path'},
          {'hrsh7th/cmp-cmdline'},
          {'saadparwaiz1/cmp_luasnip'},
          {'hrsh7th/cmp-nvim-lsp'},
          {'hrsh7th/cmp-nvim-lua'},

          -- Snippets
          {'L3MON4D3/LuaSnip'},
          {'rafamadriz/friendly-snippets'},
      }
  }

  -- use("folke/zen-mode.nvim")
    use('rebelot/kanagawa.nvim')
    use({
      'rose-pine/neovim',
      as = 'rose-pine',
      config = function()
          variant = 'moon'
          vim.cmd('colorscheme rose-pine')
          disable_background = true
          disable_float_background = true

          groups = {
              background = '2b3e50'
            }
      end
    })

    if packer_bootstrap then
        require('packer').sync()
    end
end)
