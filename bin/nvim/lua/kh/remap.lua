-- vim.g.mapleader = " " -- moved to init.lua (must be set before lazy.nvim loads)

-- vim.keymap.set("n", "<leader>vpp", "<cmd>e ~/.config/nvim/lua/kh/packer.lua<CR>");
vim.keymap.set("n", "<leader>vpp", "<cmd>e ~/.config/nvim/lua/kh/lazy.lua<CR>")


vim.keymap.set("n", "<leader><leader>", function()
    vim.cmd("so")
end)

vim.keymap.set("n", "<C-s>", "<cmd>:w<CR>")
