
local augroup = vim.api.nvim_create_augroup
local khire_augroup = augroup('khire', {})

local autocmd = vim.api.nvim_create_autocmd

function R(name)
    require("plenary.reload").relod_module(name)
end
