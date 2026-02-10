local status_ok, builtin = pcall(require, 'telescope.builtin')
if not status_ok then
    return
end

vim.keymap.set('n', '<leader>ff', builtin.find_files, {})
vim.keymap.set('n', '<leader>fg', builtin.live_grep, {})
vim.keymap.set('n', '<leader>fb', builtin.buffers, {})
vim.keymap.set('n', '<leader>fh', builtin.help_tags, {})

local actions_ok, actions = pcall(require, 'telescope.actions')
if not actions_ok then
    return
end

local trouble_ok, trouble = pcall(require, 'trouble.sources.telescope')
if not trouble_ok then
    return
end

local telescope_ok, telescope = pcall(require, 'telescope')
if not telescope_ok then
    return
end

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

