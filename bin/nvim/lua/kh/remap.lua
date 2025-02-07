vim.g.mapleader = " "

vim.keymap.set("n", "<leader>vpp", "<cmd>e ~/.config/nvim/lua/kh/packer.lua<CR>");

vim.keymap.set("n", "<leader><leader>", function()
    vim.cmd("so")
end)

vim.keymap.set("n", "<C-s>", "<cmd>:w<CR>")
