local lsp = require("lsp-zero")
local utils = require("utils")


-- Fix Undefined global 'vim'
-- lsp.nvim_workspace()

local cmp = require("cmp")
local cmp_select = {behavior = cmp.SelectBehavior.Select}


local custom_attach = function(client, bufnr)
  local opts = {buffer = bufnr, remap = false}

  vim.keymap.set("n", "gd", function() vim.lsp.buf.definition() end, opts)
  vim.keymap.set("n", "K", function() vim.lsp.buf.hover() end, opts)
  vim.keymap.set("n", "<leader>vws", function() vim.lsp.buf.workspace_symbol() end, opts)
  vim.keymap.set("n", "<leader>vd", function() vim.diagnostic.open_float() end, opts)
  vim.keymap.set("n", "[d", function() vim.diagnostic.goto_next() end, opts)
  vim.keymap.set("n", "]d", function() vim.diagnostic.goto_prev() end, opts)
  vim.keymap.set("n", "<leader>vca", function() vim.lsp.buf.code_action() end, opts)
  vim.keymap.set("n", "<leader>vrr", function() vim.lsp.buf.references() end, opts)
  vim.keymap.set("n", "<leader>vrn", function() vim.lsp.buf.rename() end, opts)
  vim.keymap.set("i", "<C-h>", function() vim.lsp.buf.signature_help() end, opts)
end

lsp.on_attach(custom_attach)
lsp.setup()
require("mason").setup()

require("mason-lspconfig").setup({
    ensure_installed = {
        'snyk_ls',
        'typos_lsp',
        'terraformls',
        'pylsp',
    },
    handlers = {
        lsp.default_setup,
        lua_ls = function()
            local lua_opts = lsp.nvim_lua_ls()
            require('lspconfig').lua_ls.setup(lua_opts)
        end,
    },
})

local cmp_action = lsp.cmp_action()

-- require('luasnip.loaders.from_vscode').lazy_load()

cmp.setup({
    sources = cmp.config.sources({
        {name = 'path'},
        {name = 'nvim_lsp'},
        {name = 'luasnip'},
    }),
    window = {
        completion = cmp.config.window.bordered(),
        documentation = cmp.config.window.bordered(),
    },
    -- default keybindings for nvim-cmp are here:
    -- https://github.com/VonHeikemen/lsp-zero.nvim/blob/v3.x/README.md#keybindings-1
    mapping = cmp.mapping.preset.insert({
    -- confirm completion item
    ['<Enter>'] = cmp.mapping.confirm({ select = true }),
    ['<Tab>'] = cmp_action.tab_complete(),
    ['<S-Tab>'] = cmp_action.select_prev_or_fallback(),

    -- trigger completion menu
    ['<C-Space>'] = cmp.mapping.complete(),

    -- scroll up and down the documentation window
    ['<C-u>'] = cmp.mapping.scroll_docs(-4),
    ['<C-d>'] = cmp.mapping.scroll_docs(4),

    -- navigate between snippet placeholders
    ['<C-f>'] = cmp_action.luasnip_jump_forward(),
    ['<C-b>'] = cmp_action.luasnip_jump_backward(),
    }),
    -- note: if you are going to use lsp-kind (another plugin)
    -- replace the line below with the function from lsp-kind
})

if utils.executable("pylsp") then
    local venv_path = os.getenv('VIRTUAL_ENV')
    local py_path = nil
    -- decide which python executable to use for mypy
    if venv_path ~= nil then
        py_path = venv_path .. "/bin/python3"
    else
        py_path = "/opt/python3.10/bin/python3"
    end


    lspconfig = require("lspconfig")
    lspconfig.pylsp.setup {
        on_attach = custom_attach,
        settings = {
            pylsp = {
                plugins = {
                    black = { enabled = true },
                    autopep8 = { enabled = false },
                     yapf = { enabled = false },
                    -- linter options
                    pylint = { enabled = true, executable = "pylint" },
                    pyflakes = { enabled = false },
                    pycodestyle = { enabled = false },
                    -- type checker
                    pylsp_mypy = { enabled = true },
                    -- auto-completion options
                    jedi_completion = { fuzzy = true },
                    -- import sorting
                    pyls_isort = { enabled = true },
                }
            }
        },
        flags = {
            debounce_text_changes = 200,
        },
        capabilities = capabilities,
    }
else
    vim.notify("pylsp not found", vim.log.levels.WARN, { title = "Nvim-config" })
end
