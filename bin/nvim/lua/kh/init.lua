-- require("kh.packer")
vim.g.mapleader = " "
require("kh.lazy")
require("kh.set")
require("kh.remap")
require("kh.telescope-pc").setup()


local augroup = vim.api.nvim_create_augroup
local khgroup = augroup('kh', {})

local autocmd = vim.api.nvim_create_autocmd
local yank_group = augroup('HighlightYank', {})

function R(name)
    require("plenary.reload").reload_module(name)
end

autocmd('TextYankPost', {
    group = yank_group,
    pattern = '*',
    callback = function()
        vim.highlight.on_yank({
            higroup = 'IncSearch',
            timeout = 40,
        })
    end,
})

autocmd({"BufWritePre"}, {
    group = khgroup,
    pattern = "*",
    command = [[%s/\s\+$//e]],
})

autocmd({"TextChanged", "TextChangedI"}, {
    group = khgroup,
    pattern = "*/claude-prompt-*.md",
    callback = function()
        local backup = vim.fn.expand("~/.claude/prompt-backups/")
        vim.fn.mkdir(backup, "p")
        local fname = vim.fn.expand("%:t")
        vim.fn.writefile(vim.fn.getline(1, "$"), backup .. fname)
    end,
})

vim.g.netrw_browse_split = 0
vim.g.netrw_banner = 0
vim.g.netrw_winsize = 25

-- local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
-- if not vim.loop.fs_stat(lazypath) then
--  vim.fn.system({
--      "git",
--      "clone",
--      "--filter=blob:none",
--      "https://github.com/folke/lazy.nvim.git",
--      "--branch=stable",
--      lazypath,
--  })
-- end
-- vim.opt.rtp:prepend(lazypath)
-- require("lazy").setup(plugins, opts)
