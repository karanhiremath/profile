local builtin = require('telescope.builtin')
vim.keymap.set('n', '<leader>ff', builtin.find_files, {})
vim.keymap.set('n', '<leader>fg', builtin.live_grep, {})
vim.keymap.set('n', '<leader>fb', builtin.buffers, {})
vim.keymap.set('n', '<leader>fh', builtin.help_tags, {})

local actions = require('telescope.actions')
local trouble = require('trouble.sources.telescope')

local telescope = require('telescope')

telescope.setup {
    defaults ={
        mappings = {
        },
    },
    vimgrep_arguments = {
        'rg',
        '--with-filename',
        '--line-number',
        '--column',
        '--smart-case',
        '--ignore-file',
        '.gitignore'
    }
}

