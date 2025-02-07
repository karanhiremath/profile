vim.opt.laststatus = 3
vim.opt.statusline =
require('rose-pine').setup({
    disable_background = true,
    disable_float_background = true,
    highlight_groups = {
        StatusLine = { fg = "gold", bg="gold", blend = 10 },
        StatusLineNC = { fg = "subtle", bg = "surface" },
    }
})

function ColorMyPencils(color)
	color = color or "rose-pine"
    vim.api.nvim_create_autocmd("ColorScheme", {
        pattern = "*",
        callback = function()
            vim.api.nvim_set_hl(0, "Normal", { bg = "none" })
            vim.api.nvim_set_hl(0, "NormalFloat", { bg = "none" })
        end,
    })

	vim.cmd.colorscheme(color)

	vim.api.nvim_set_hl(0, "Normal", { bg = "none" })
	vim.api.nvim_set_hl(0, "NormalFloat", { bg = "none" })

end

ColorMyPencils()
