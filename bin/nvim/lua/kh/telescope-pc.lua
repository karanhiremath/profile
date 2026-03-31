-- telescope-pc: pi-code project picker & tmux pi-pane controls
-- Keybinds:
--   <leader>fp  — telescope project picker (launch/attach/kill sessions)
--   <leader>pt  — toggle focus between nvim and pi pane
--   <leader>ps  — send current file path to pi pane
--   <leader>pk  — restart pi in the right pane
--   <leader>pc  — send "continue" flag to pi (restart with -c)

local pickers = require("telescope.pickers")
local finders = require("telescope.finders")
local conf = require("telescope.config").values
local actions = require("telescope.actions")
local action_state = require("telescope.actions.state")
local previewers = require("telescope.previewers")

local M = {}

local SRC_DIR = vim.fn.expand("~/src")
local SESSION_PREFIX = "pi" -- tmux session names use pi_ prefix (e.g. pi_bifrost)
local PI_BIN = vim.fn.exepath("pi") ~= "" and vim.fn.exepath("pi") or "/opt/homebrew/bin/pi"

-- ── Helpers ────────────────────────────────────────────
local function run(cmd)
  local handle = io.popen(cmd .. " 2>/dev/null")
  if not handle then return "" end
  local result = handle:read("*a")
  handle:close()
  return result
end

local function session_name(project)
  return SESSION_PREFIX .. "_" .. project
end

local function get_projects()
  local pc_bin = os.getenv("PROFILE_DIR") or (os.getenv("HOME") .. "/src/profile")
  local raw = run(pc_bin .. "/bin/pc --list")
  local projects = {}
  for line in raw:gmatch("[^\n]+") do
    local status, name, path = line:match("^(%S+)\t(%S+)\t(.+)$")
    if name then
      table.insert(projects, { status = status, name = name, path = path })
    end
  end
  return projects
end

local function is_in_pc_session()
  local sess = vim.fn.system("tmux display-message -p '#{session_name}' 2>/dev/null"):gsub("%s+", "")
  return sess:match("^" .. SESSION_PREFIX .. "_")
end

local function current_project()
  local sess = vim.fn.system("tmux display-message -p '#{session_name}' 2>/dev/null"):gsub("%s+", "")
  return sess:match("^" .. SESSION_PREFIX .. "_(.+)$")
end

-- Layout: pane 0 = nvim (top-left), pane 1 = pi (right), pane 2 = zsh (bottom-left)
local function pane_id(index)
  local sess = vim.fn.system("tmux display-message -p '#{session_name}' 2>/dev/null"):gsub("%s+", "")
  return sess .. "." .. index
end

local function pi_pane_id()
  return pane_id(1)
end

local function zsh_pane_id()
  return pane_id(2)
end

-- ── Telescope Picker ───────────────────────────────────
function M.pick_project(opts)
  opts = opts or {}
  local projects = get_projects()

  pickers.new(opts, {
    prompt_title = "Pi Projects",
    finder = finders.new_table({
      results = projects,
      entry_maker = function(entry)
        local icon = entry.status == "active" and "● " or "  "
        local display = icon .. entry.name
        return {
          value = entry,
          display = display,
          ordinal = entry.name,
          path = entry.path,
        }
      end,
    }),
    sorter = conf.generic_sorter(opts),
    previewer = previewers.new_termopen_previewer({
      get_command = function(entry)
        local p = entry.value
        if p.status == "active" then
          return { "tmux", "capture-pane", "-t", session_name(p.name) .. ".1", "-p" }
        else
          return { "ls", "-1", "--color=always", p.path }
        end
      end,
    }),
    attach_mappings = function(prompt_bufnr, map)
      -- Enter: launch/attach session
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local entry = action_state.get_selected_entry()
        if not entry then return end
        local p = entry.value
        -- Use tmux to switch/create
        vim.fn.system("pc " .. vim.fn.shellescape(p.name))
      end)

      -- Ctrl-k: kill session
      map("i", "<C-k>", function()
        local entry = action_state.get_selected_entry()
        if not entry then return end
        local p = entry.value
        if p.status == "active" then
          vim.fn.system("tmux kill-session -t " .. vim.fn.shellescape(session_name(p.name)))
          vim.notify("Killed session: " .. p.name, vim.log.levels.WARN)
          -- Refresh picker
          actions.close(prompt_bufnr)
          M.pick_project(opts)
        else
          vim.notify("Session not active: " .. p.name, vim.log.levels.INFO)
        end
      end)

      -- Ctrl-c: continue last pi conversation in session
      map("i", "<C-r>", function()
        actions.close(prompt_bufnr)
        local entry = action_state.get_selected_entry()
        if not entry then return end
        local p = entry.value
        vim.fn.system("pc " .. vim.fn.shellescape(p.name) .. " -- -c")
      end)

      return true
    end,
  }):find()
end

-- ── Pane Controls ──────────────────────────────────────
-- Layout: pane 0 = nvim (top-left), pane 1 = pi (right), pane 2 = zsh (bottom-left)

-- Toggle focus to pi pane (right), or back to nvim
function M.toggle_pi_pane()
  if not is_in_pc_session() then
    vim.notify("Not in a pc session", vim.log.levels.WARN)
    return
  end
  local current = vim.fn.system("tmux display-message -p '#{pane_index}' 2>/dev/null"):gsub("%s+", "")
  if current == "1" then
    vim.fn.system("tmux select-pane -t " .. pane_id(0))
  else
    vim.fn.system("tmux select-pane -t " .. pi_pane_id())
  end
end

-- Toggle focus to zsh pane (bottom-left), or back to nvim
function M.toggle_zsh_pane()
  if not is_in_pc_session() then
    vim.notify("Not in a pc session", vim.log.levels.WARN)
    return
  end
  local current = vim.fn.system("tmux display-message -p '#{pane_index}' 2>/dev/null"):gsub("%s+", "")
  if current == "2" then
    vim.fn.system("tmux select-pane -t " .. pane_id(0))
  else
    vim.fn.system("tmux select-pane -t " .. zsh_pane_id())
  end
end

-- Send current file path to pi pane (so pi can read it)
function M.send_file_to_pi()
  if not is_in_pc_session() then
    vim.notify("Not in a pc session", vim.log.levels.WARN)
    return
  end
  local file = vim.fn.expand("%:p")
  if file == "" then
    vim.notify("No file open", vim.log.levels.WARN)
    return
  end
  -- Send the file path as text to pi's pane
  local escaped = vim.fn.shellescape(file)
  vim.fn.system("tmux send-keys -t " .. pi_pane_id() .. " " .. escaped .. " Enter")
  vim.notify("Sent to pi: " .. file)
end

-- Send arbitrary text to pi pane
function M.send_to_pi(text)
  if not is_in_pc_session() then
    vim.notify("Not in a pc session", vim.log.levels.WARN)
    return
  end
  vim.fn.system("tmux send-keys -t " .. pi_pane_id() .. " " .. vim.fn.shellescape(text) .. " Enter")
end

-- Restart pi in the right pane
function M.restart_pi(flags)
  if not is_in_pc_session() then
    vim.notify("Not in a pc session", vim.log.levels.WARN)
    return
  end
  flags = flags or ""
  local proj = current_project()
  local dir = SRC_DIR .. "/" .. proj
  local pane = pi_pane_id()
  -- Kill whatever's running, then start pi fresh
  vim.fn.system("tmux send-keys -t " .. pane .. " C-c")
  vim.defer_fn(function()
    local cmd = "cd " .. vim.fn.shellescape(dir) .. " && " .. PI_BIN
    if flags ~= "" then cmd = cmd .. " " .. flags end
    vim.fn.system("tmux send-keys -t " .. pane .. " " .. vim.fn.shellescape(cmd) .. " Enter")
    vim.notify("Restarted pi" .. (flags ~= "" and (" " .. flags) or ""))
  end, 200)
end

-- ── Keymaps ────────────────────────────────────────────
function M.setup()
  vim.keymap.set("n", "<leader>fp", M.pick_project, { desc = "Pi: pick project" })
  vim.keymap.set("n", "<leader>pt", M.toggle_pi_pane, { desc = "Pi: toggle pi pane" })
  vim.keymap.set("n", "<leader>pz", M.toggle_zsh_pane, { desc = "Pi: toggle zsh pane" })
  vim.keymap.set("n", "<leader>ps", M.send_file_to_pi, { desc = "Pi: send file to pi" })
  vim.keymap.set("n", "<leader>pk", function() M.restart_pi() end, { desc = "Pi: restart pi" })
  vim.keymap.set("n", "<leader>pc", function() M.restart_pi("-c") end, { desc = "Pi: continue last session" })
  vim.keymap.set("n", "<leader>pr", function() M.restart_pi("-r") end, { desc = "Pi: resume/pick session" })

  -- Visual mode: send selection to pi
  vim.keymap.set("v", "<leader>ps", function()
    local lines = vim.fn.getregion(vim.fn.getpos("v"), vim.fn.getpos("."), { type = vim.fn.mode() })
    if #lines == 0 then return end
    local text = table.concat(lines, "\n")
    M.send_to_pi(text)
    vim.notify("Sent " .. #lines .. " lines to pi")
  end, { desc = "Pi: send selection to pi" })
end

return M
