# Migrating from Packer to lazy.nvim

## File structure

```
lua/kh/
├── packer.lua   ← original Packer setup (kept intact)
├── lazy.lua     ← new lazy.nvim setup (drop-in replacement)
├── init.lua     ← load order: packer OR lazy (change one line to switch)
├── remap.lua
└── set.lua
```

## How to activate lazy.nvim

**1. Switch the loader in `lua/kh/init.lua`:**

```lua
-- Before (packer):
require("kh.packer")

-- After (lazy):
require("kh.lazy")
```

**2. Update the config-file keymap in `lua/kh/remap.lua`** (optional, for `<leader>vpp`):

```lua
-- Before:
vim.keymap.set("n", "<leader>vpp", "<cmd>e ~/.config/nvim/lua/kh/packer.lua<CR>")

-- After:
vim.keymap.set("n", "<leader>vpp", "<cmd>e ~/.config/nvim/lua/kh/lazy.lua<CR>")
```

**3. Clean up the old Packer install** (optional):

```bash
rm -rf ~/.local/share/nvim/site/pack/packer
```

**4. Install plugins headlessly** (used by `bin/nvim/install-plugins`):

```bash
nvim --headless "+Lazy! sync" +qa
```

---

## Daily usage

| Command | What it does |
|---------|--------------|
| `:Lazy` | Open the lazy.nvim UI |
| `:Lazy sync` | Install missing + update all plugins |
| `:Lazy update` | Update plugins (no install of new ones) |
| `:Lazy install` | Install any missing plugins |
| `:Lazy clean` | Remove plugins no longer in the spec |
| `:Lazy restore` | Roll back to the versions in `lazy-lock.json` |
| `:Lazy log` | Show recent plugin changelogs |
| `:Lazy profile` | Show plugin load-time breakdown |

> **Tip:** lazy.nvim generates a `lazy-lock.json` lockfile in your config dir (`~/.config/nvim/`). Commit this file to pin exact plugin versions across machines.

---

## Adding a plugin

Add an entry to the `require("lazy").setup({ ... })` table in `lua/kh/lazy.lua`.

**Simple plugin (no config):**
```lua
'tpope/vim-surround',
```

**Plugin with config:**
```lua
{
    'plugin/name',
    config = function()
        require("plugin").setup({
            -- options
        })
    end,
},
```

**Plugin with dependencies:**
```lua
{
    'plugin/name',
    dependencies = { 'nvim-lua/plenary.nvim' },
},
```

**Plugin that only loads for specific filetypes (lazy-loading):**
```lua
{
    'plugin/name',
    ft = { 'python', 'lua' },
},
```

**Plugin that loads on a keymap:**
```lua
{
    'plugin/name',
    keys = {
        { '<leader>x', '<cmd>PluginCmd<CR>', desc = 'Do thing' },
    },
},
```

**Pin to a specific commit or branch:**
```lua
{
    'neovim/nvim-lspconfig',
    commit = 'a981d4447b92c54a4d464eb1a76b799bc3f9a771',  -- pin to commit
    -- branch = 'master',                                  -- or pin to branch
},
```

---

## Packer → lazy.nvim cheat sheet

| Packer | lazy.nvim |
|--------|-----------|
| `use 'foo/bar'` | `'foo/bar'` |
| `requires = {...}` | `dependencies = {...}` |
| `run = fn` | `build = fn` |
| `config = fn` | `config = fn` (same) |
| `after = 'x'` | `dependencies = {'x'}` |
| `branch = 'x'` | `branch = 'x'` (same) |
| `commit = 'x'` | `commit = 'x'` (same) |
| `ft = 'x'` | `ft = 'x'` (same) |
| `keys = {...}` | `keys = {...}` (same) |
| `:PackerSync` | `:Lazy sync` |
| `:PackerClean` | `:Lazy clean` |
| `:PackerStatus` | `:Lazy` |
