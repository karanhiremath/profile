vim.g.mapleader = " "

vim.keymap.set("n", "<leader>vpp", "<cmd>e ~/.dotfiles/nvim/.config/nvim/lua/theprimeagen/packer.lua<CR>");
 
vim.keymap.set("n", "<leader><leader>", function()
    vim.cmd("so")
end)


