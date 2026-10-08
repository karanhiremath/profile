-- Telescope picker for live/on-disk prompt buffers across harnesses.
-- Opened by `atop vi` / `a-top vi` / `bin/atop/vi`. Never tmux send-keys.

local M = {}

local function decode_catalog(path)
  local f = io.open(path, "r")
  if not f then return { entries = {} } end
  local raw = f:read("*a")
  f:close()
  local ok, data = pcall(vim.json.decode, raw)
  if not ok or type(data) ~= "table" then return { entries = {} } end
  return data
end

local function coordinator_buf()
  local path = os.getenv("ATOP_VI_COORD")
  if type(path) == "string" and path ~= "" then
    vim.cmd.edit(vim.fn.fnameescape(path))
    vim.bo.filetype = "markdown"
    return vim.api.nvim_get_current_buf()
  end
  local buf = vim.api.nvim_create_buf(true, false)
  vim.api.nvim_buf_set_name(buf, "atop-vi")
  vim.bo[buf].filetype = "markdown"
  vim.bo[buf].buftype = ""
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, {
    "# atop-vi",
    "",
    "Telescope: prompt buffers for herm / pi / claude / codex / cursor / others.",
    "<CR> edit   <leader>fv reopen picker   :q leaves this coordinator buffer",
    "",
  })
  vim.api.nvim_set_current_buf(buf)
  return buf
end

function M.pick(opts)
  opts = opts or {}
  local ok_t = pcall(require, "telescope")
  if not ok_t then
    vim.notify("telescope not loaded", vim.log.levels.ERROR)
    return
  end
  local pickers = require("telescope.pickers")
  local finders = require("telescope.finders")
  local conf = require("telescope.config").values
  local actions = require("telescope.actions")
  local action_state = require("telescope.actions.state")
  local previewers = require("telescope.previewers")

  local catalog_path = opts.catalog or os.getenv("ATOP_VI_CATALOG")
  local catalog = catalog_path and decode_catalog(catalog_path) or { entries = {} }
  local entries = catalog.entries or {}

  pickers.new(opts, {
    prompt_title = "atop-vi  harness prompts",
    finder = finders.new_table({
      results = entries,
      entry_maker = function(entry)
        local live = entry.live and "live" or "disk"
        local display = string.format("%-9s %-5s %s", entry.harness or "?", live, entry.id or entry.path)
        return {
          value = entry,
          display = display,
          ordinal = table.concat({
            entry.harness or "",
            entry.id or "",
            entry.path or "",
          }, " "),
          path = entry.path,
        }
      end,
    }),
    sorter = conf.generic_sorter(opts),
    previewer = previewers.new_termopen_previewer({
      get_command = function(entry)
        local p = entry.value.path
        if p and vim.fn.filereadable(p) == 1 then
          return { "sed", "-n", "1,80p", p }
        end
        return { "printf", "%s\n", "(unreadable) " .. tostring(p) }
      end,
    }),
    attach_mappings = function(prompt_bufnr, map)
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local sel = action_state.get_selected_entry()
        if not sel or not sel.value or not sel.value.path then return end
        vim.cmd.edit(vim.fn.fnameescape(sel.value.path))
      end)
      map("i", "<C-r>", function()
        actions.close(prompt_bufnr)
        M.open({ refresh = true })
      end)
      return true
    end,
  }):find()
end

function M.refresh_catalog()
  local vi = os.getenv("ATOP_VI") or (os.getenv("HOME") .. "/src/profile/bin/atop/vi")
  local dest = os.getenv("ATOP_VI_CATALOG")
    or (vim.fn.stdpath("cache") .. "/atop-vi.catalog.json")
  local out = vim.fn.system({ vi, "catalog" })
  if vim.v.shell_error == 0 and out ~= "" then
    vim.fn.writefile(vim.split(out, "\n", { plain = true }), dest)
    vim.fn.setenv("ATOP_VI_CATALOG", dest)
  end
  return dest
end

function M.open(opts)
  opts = opts or {}
  if vim.fn.bufname("%") == "" or vim.fn.bufname("%") == "atop-vi" then
    coordinator_buf()
  end
  if opts.refresh then
    opts.catalog = M.refresh_catalog()
  end
  vim.schedule(function()
    M.pick(opts)
  end)
end

function M.setup()
  vim.keymap.set("n", "<leader>fv", function()
    M.open({})
  end, { desc = "atop-vi: harness prompt picker" })
end

return M
