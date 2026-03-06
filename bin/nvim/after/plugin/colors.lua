vim.opt.laststatus = 3
vim.opt.statusline = table.concat {
  "%<%f%h%m%r",          -- path, readonly, modified
  " %#StatusLineNC#",
  " %{&ff} %{&fenc}",   -- fileformat + encoding
  "%*",
  " %=%y",              -- filetype, right‑aligned
  " %P %l:%c",          -- percentage + line:col
}


-- Transparent defaults
local transparent_groups = {
  'Normal', 'NormalFloat', 'FloatBorder', 'Pmenu', 'PmenuSel',
  'SignColumn', 'MsgArea', 'LineNr', 'NonText'
}
for _, group in ipairs(transparent_groups) do
  vim.api.nvim_set_hl(0, group, { bg = nil })
end
