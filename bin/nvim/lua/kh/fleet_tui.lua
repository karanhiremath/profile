--- fleet_tui.lua: Rich TUI fleet command center inside telescope
---
--- A multi-view telescope interface for fleet management. The left panel
--- lists agents; the right panel shows a live preview that switches between
--- views via Ctrl-key bindings.
---
--- Views (switch with Ctrl-<key> inside the picker):
---   default       Live pane capture of selected agent
---   <C-d>         Dashboard: fleet-wide status + type breakdown + metrics
---   <C-g>         Git: diff --stat + recent commits for selected agent
---   <C-m>         Messages: last steering inputs / user messages
---   <C-p>         Progress: visual progress bars, file change counts
---   <C-i>         Info: agent metadata, session dir, spawn command
---   <C-x>         External tools: k9s, btop, etc (pluggable)
---
--- Actions:
---   <CR>          Jump to agent pane
---   <C-s>         Send steering text to agent
---   <C-n>         Spawn new agent (type picker)
---   <C-k>         Kill agent
---   <C-f>         Send current file to agent
---   <C-r>         Restart agent with continue flag
---   <C-t>         Telemetry + optimization proposals
---   <C-b>         Broadcast message to all waiting agents
---
--- Keybind: <leader>dd (fleet TUI)

local M = {}

local registry = require("kh.agent_registry")
local fleet    = require("kh.fleet")

-- ── View Modes ────────────────────────────────────────

-- Each view is a function(agent) -> string[] (lines to display in preview)
M.views = {}
M.current_view = "pane"
M.view_order = { "pane", "dashboard", "git", "messages", "progress", "info", "tools" }

-- Separator + header helpers
local function header(title, width)
  width = width or 60
  local pad = width - #title - 4
  if pad < 2 then pad = 2 end
  return "── " .. title .. " " .. string.rep("─", pad)
end

local function bar(value, max, width)
  width = width or 30
  if max == 0 then return string.rep("░", width) end
  local filled = math.floor((value / max) * width)
  return string.rep("█", filled) .. string.rep("░", width - filled)
end

-- ── View: Pane (default) ──────────────────────────────
-- Live capture of the agent's tmux pane
M.views.pane = function(agent)
  if not agent then return { "(no agent selected)" } end
  local cap = vim.fn.system(
    "tmux capture-pane -t " .. vim.fn.shellescape(agent.target) .. " -p -e 2>/dev/null")
  return vim.split(cap, "\n")
end

-- ── View: Dashboard ───────────────────────────────────
-- Fleet-wide status overview
M.views.dashboard = function(_agent)
  local agents = fleet.scan({ include_git = true })
  local lines = {}

  -- Header
  lines[#lines + 1] = header("Fleet Dashboard")
  lines[#lines + 1] = string.format("  Registry v%s  |  %d agents active", registry.VERSION, #agents)
  lines[#lines + 1] = ""

  -- Status counts
  local counts = { waiting = 0, working = 0, init = 0, idle = 0 }
  for _, a in ipairs(agents) do
    counts[a.status] = (counts[a.status] or 0) + 1
  end
  lines[#lines + 1] = string.format("  ⏳ Waiting: %d   ⚙️  Working: %d   ✳ Init: %d   💤 Idle: %d",
    counts.waiting, counts.working, counts.init, counts.idle)
  lines[#lines + 1] = ""

  -- Type breakdown with visual bars
  lines[#lines + 1] = header("Agent Types")
  local by_type = {}
  for _, a in ipairs(agents) do
    by_type[a.agent_type] = (by_type[a.agent_type] or 0) + 1
  end
  for _, key in ipairs(registry.order) do
    local count = by_type[key] or 0
    if count > 0 then
      local def = registry.get(key)
      lines[#lines + 1] = string.format("  %s %-12s %s %d",
        def.icon, def.label, bar(count, #agents, 20), count)
    end
  end
  lines[#lines + 1] = ""

  -- Project breakdown
  lines[#lines + 1] = header("Projects")
  local by_proj = {}
  for _, a in ipairs(agents) do
    by_proj[a.project] = by_proj[a.project] or { agents = {}, changes = 0 }
    table.insert(by_proj[a.project].agents, a)
    if a.git_context then
      by_proj[a.project].changes = by_proj[a.project].changes + a.git_context.changed_files
    end
  end
  local projs = vim.tbl_keys(by_proj)
  table.sort(projs, function(a, b) return #by_proj[a].agents > #by_proj[b].agents end)
  for _, proj in ipairs(projs) do
    local info = by_proj[proj]
    local type_icons = {}
    for _, a in ipairs(info.agents) do
      type_icons[#type_icons + 1] = a.agent_def.icon .. registry.status_icons[a.status]
    end
    local change_str = info.changes > 0
      and string.format("  (%d files changed)", info.changes)
      or ""
    lines[#lines + 1] = string.format("  %-18s %s%s",
      proj, table.concat(type_icons, " "), change_str)
  end
  lines[#lines + 1] = ""

  -- Attention queue: waiting agents sorted by project
  if counts.waiting > 0 then
    lines[#lines + 1] = header("Attention Queue")
    for _, a in ipairs(agents) do
      if a.status == "waiting" then
        lines[#lines + 1] = string.format("  ⏳ %s %s  [%s]  → needs steering",
          a.agent_def.icon, a.project, a.target)
      end
    end
    lines[#lines + 1] = ""
  end

  -- Quick telemetry if available
  local stats = fleet.aggregate_telemetry(7)
  if stats.total_events > 0 then
    lines[#lines + 1] = header("7d Telemetry")
    lines[#lines + 1] = string.format("  Events: %d  Spawns: %d  Steers: %d  Kills: %d",
      stats.total_events, stats.spawn_count, stats.steer_count, stats.kill_count)
    if stats.avg_wait_seconds then
      lines[#lines + 1] = string.format("  Avg wait: %.0fs", stats.avg_wait_seconds)
    end
  end

  return lines
end

-- ── View: Git ─────────────────────────────────────────
-- Git diff + recent commits for the selected agent's project
M.views.git = function(agent)
  if not agent then return { "(no agent selected)" } end
  local lines = {}
  local path = agent.path

  lines[#lines + 1] = header(agent.agent_def.icon .. " " .. agent.project .. " — Git")

  -- Branch
  local branch = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " branch --show-current 2>/dev/null")
  lines[#lines + 1] = "  Branch: " .. vim.trim(branch)
  lines[#lines + 1] = ""

  -- Diff stat
  local stat = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " diff --stat 2>/dev/null")
  if vim.trim(stat) ~= "" then
    lines[#lines + 1] = header("Uncommitted Changes")
    for _, l in ipairs(vim.split(stat, "\n")) do
      if l ~= "" then lines[#lines + 1] = "  " .. l end
    end
  else
    lines[#lines + 1] = "  (no uncommitted changes)"
  end
  lines[#lines + 1] = ""

  -- Staged
  local staged = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " diff --cached --stat 2>/dev/null")
  if vim.trim(staged) ~= "" then
    lines[#lines + 1] = header("Staged")
    for _, l in ipairs(vim.split(staged, "\n")) do
      if l ~= "" then lines[#lines + 1] = "  " .. l end
    end
    lines[#lines + 1] = ""
  end

  -- Recent commits
  lines[#lines + 1] = header("Recent Commits")
  local log = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " log --oneline -10 2>/dev/null")
  for _, l in ipairs(vim.split(log, "\n")) do
    if l ~= "" then lines[#lines + 1] = "  " .. l end
  end

  -- Worktrees
  local wt = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " worktree list 2>/dev/null")
  if vim.trim(wt) ~= "" then
    lines[#lines + 1] = ""
    lines[#lines + 1] = header("Worktrees")
    for _, l in ipairs(vim.split(wt, "\n")) do
      if l ~= "" then lines[#lines + 1] = "  " .. l end
    end
  end

  return lines
end

-- ── View: Messages ────────────────────────────────────
-- Recent steering inputs / user messages from session files
M.views.messages = function(agent)
  if not agent then return { "(no agent selected)" } end
  local lines = {}
  lines[#lines + 1] = header(agent.agent_def.icon .. " " .. agent.project .. " — Messages")
  lines[#lines + 1] = ""

  -- Try to read from pi session files
  if agent.agent_type == "pi" then
    local session_dir = vim.fn.expand("~/.pi/agent/sessions")
    local enc_path = "--" .. agent.path:gsub("^/", ""):gsub("/", "-") .. "--"
    local dir = session_dir .. "/" .. enc_path
    local files = vim.fn.glob(dir .. "/*.jsonl", false, true)
    if #files > 0 then
      table.sort(files, function(a, b) return vim.fn.getftime(a) < vim.fn.getftime(b) end)
      local latest = files[#files]
      local all_lines = vim.fn.readfile(latest)
      local msg_count = 0
      -- Read last 200 lines for messages
      local start = math.max(1, #all_lines - 200)
      for i = #all_lines, start, -1 do
        if msg_count >= 15 then break end
        local ok, entry = pcall(vim.fn.json_decode, all_lines[i])
        if ok and entry and entry.type == "message" and entry.message then
          local role = entry.message.role
          local content = ""
          if type(entry.message.content) == "string" then
            content = entry.message.content:sub(1, 100):gsub("\n", " ")
          elseif type(entry.message.content) == "table" then
            for _, block in ipairs(entry.message.content) do
              if block.type == "text" then
                content = block.text:sub(1, 100):gsub("\n", " ")
                break
              end
            end
          end
          if content ~= "" then
            local icon = role == "user" and "👤" or "🤖"
            lines[#lines + 1] = string.format("  %s %s", icon, content)
            msg_count = msg_count + 1
          end
        end
      end
      if msg_count == 0 then
        lines[#lines + 1] = "  (no messages found in session)"
      end
    else
      lines[#lines + 1] = "  (no session files found)"
    end
  else
    -- For non-pi agents, show last N lines from pane capture as proxy
    lines[#lines + 1] = "  (session file reading for " .. agent.agent_type .. " not yet supported)"
    lines[#lines + 1] = "  Showing last pane output:"
    lines[#lines + 1] = ""
    local cap = vim.fn.system(
      "tmux capture-pane -t " .. vim.fn.shellescape(agent.target) .. " -p 2>/dev/null")
    local cap_lines = vim.split(cap, "\n")
    local start = math.max(1, #cap_lines - 20)
    for i = start, #cap_lines do
      lines[#lines + 1] = "  " .. (cap_lines[i] or "")
    end
  end

  -- Telemetry: recent steers for this project
  lines[#lines + 1] = ""
  lines[#lines + 1] = header("Fleet Telemetry Steers")
  local tdir = vim.fn.expand("~/.config/fleet/telemetry")
  local steer_count = 0
  for d = 0, 6 do
    local date_str = os.date("%Y-%m-%d", os.time() - d * 86400)
    local path = tdir .. "/" .. date_str .. ".jsonl"
    local f = io.open(path, "r")
    if f then
      for line in f:lines() do
        local ok, event = pcall(vim.fn.json_decode, line)
        if ok and event and event.event == "steer" and event.project == agent.project then
          steer_count = steer_count + 1
        end
      end
      f:close()
    end
  end
  lines[#lines + 1] = string.format("  %d steering inputs in last 7 days", steer_count)

  return lines
end

-- ── View: Progress ────────────────────────────────────
-- Visual progress: file change counts, bars, activity over time
M.views.progress = function(agent)
  if not agent then return { "(no agent selected)" } end
  local lines = {}
  lines[#lines + 1] = header(agent.agent_def.icon .. " " .. agent.project .. " — Progress")
  lines[#lines + 1] = ""

  local path = agent.path

  -- Current changes
  local stat = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " diff --shortstat 2>/dev/null")
  stat = vim.trim(stat)
  local files_changed = tonumber(stat:match("(%d+) file")) or 0
  local insertions    = tonumber(stat:match("(%d+) insertion")) or 0
  local deletions     = tonumber(stat:match("(%d+) deletion")) or 0
  local total_lines   = insertions + deletions

  lines[#lines + 1] = "  Files changed:  " .. bar(files_changed, math.max(files_changed, 20), 25) .. " " .. files_changed
  lines[#lines + 1] = "  Insertions:     " .. bar(insertions, math.max(total_lines, 100), 25) .. " +" .. insertions
  lines[#lines + 1] = "  Deletions:      " .. bar(deletions, math.max(total_lines, 100), 25) .. " -" .. deletions
  lines[#lines + 1] = ""

  -- Commit activity (last 24h)
  lines[#lines + 1] = header("Commit Activity (24h)")
  local log = vim.fn.system("git -C " .. vim.fn.shellescape(path)
    .. " log --oneline --since='24 hours ago' 2>/dev/null")
  local commits = vim.split(vim.trim(log), "\n")
  local commit_count = (commits[1] ~= "") and #commits or 0
  lines[#lines + 1] = "  Commits: " .. bar(commit_count, math.max(commit_count, 10), 25) .. " " .. commit_count
  lines[#lines + 1] = ""

  -- Commit activity by hour (sparkline)
  lines[#lines + 1] = header("Hourly Activity (24h)")
  local hourly = {}
  local max_hourly = 0
  for h = 0, 23 do hourly[h] = 0 end
  local hour_log = vim.fn.system("git -C " .. vim.fn.shellescape(path)
    .. " log --format='%H' --since='24 hours ago' 2>/dev/null")
  for h_str in hour_log:gmatch("(%d+)") do
    local h = tonumber(h_str) or 0
    hourly[h] = hourly[h] + 1
    if hourly[h] > max_hourly then max_hourly = hourly[h] end
  end
  local sparkline_chars = { "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█" }
  local spark = "  "
  for h = 0, 23 do
    if max_hourly == 0 then
      spark = spark .. "▁"
    else
      local idx = math.ceil((hourly[h] / max_hourly) * 7) + 1
      idx = math.min(idx, 8)
      if hourly[h] == 0 then idx = 1 end
      spark = spark .. sparkline_chars[idx]
    end
  end
  lines[#lines + 1] = spark
  lines[#lines + 1] = "  0         6         12        18       23"
  lines[#lines + 1] = ""

  -- Agent status duration estimate
  lines[#lines + 1] = header("Agent Status")
  lines[#lines + 1] = string.format("  Type:    %s %s", agent.agent_def.icon, agent.agent_def.label)
  lines[#lines + 1] = string.format("  Status:  %s %s", registry.status_icons[agent.status] or "?", agent.status)
  lines[#lines + 1] = string.format("  Target:  %s", agent.target)
  lines[#lines + 1] = string.format("  PID:     %s", agent.pid)

  return lines
end

-- ── View: Info ────────────────────────────────────────
-- Agent metadata, configuration, session details
M.views.info = function(agent)
  if not agent then return { "(no agent selected)" } end
  local lines = {}
  local def = agent.agent_def

  lines[#lines + 1] = header(def.icon .. " " .. def.label .. " — Info")
  lines[#lines + 1] = ""

  lines[#lines + 1] = "  Agent Type:     " .. def.type
  lines[#lines + 1] = "  Label:          " .. def.label
  lines[#lines + 1] = "  Icon:           " .. def.icon
  lines[#lines + 1] = "  Project:        " .. agent.project
  lines[#lines + 1] = "  Working Dir:    " .. agent.path
  lines[#lines + 1] = "  Tmux Target:    " .. agent.target
  lines[#lines + 1] = "  Session:        " .. agent.session
  lines[#lines + 1] = "  Window:         " .. agent.window .. " (idx:" .. agent.win_idx .. ")"
  lines[#lines + 1] = "  Pane:           " .. agent.pane
  lines[#lines + 1] = "  PID:            " .. agent.pid
  lines[#lines + 1] = "  Status:         " .. agent.status
  lines[#lines + 1] = ""

  lines[#lines + 1] = header("Spawn Config")
  lines[#lines + 1] = "  Binary:         " .. def.spawn.cmd
  local bin_path = vim.fn.exepath(def.spawn.cmd)
  lines[#lines + 1] = "  Resolved Path:  " .. (bin_path ~= "" and bin_path or "(not found)")
  lines[#lines + 1] = "  Default Args:   " .. (table.concat(def.spawn.default_args, " "))
  lines[#lines + 1] = "  Continue Flag:  " .. (def.spawn.continue_flag ~= "" and def.spawn.continue_flag or "(none)")
  lines[#lines + 1] = ""

  lines[#lines + 1] = header("Session Storage")
  local sess_dir = registry.expand_path(def.session.dir)
  lines[#lines + 1] = "  Directory:      " .. (sess_dir or "(none)")
  lines[#lines + 1] = "  File Pattern:   " .. (def.session.file_pattern ~= "" and def.session.file_pattern or "(none)")
  if sess_dir and vim.fn.isdirectory(sess_dir) == 1 then
    local count = vim.fn.system("ls -1 " .. vim.fn.shellescape(sess_dir) .. " 2>/dev/null | wc -l"):gsub("%s+", "")
    lines[#lines + 1] = "  Session Count:  " .. count
  end
  lines[#lines + 1] = ""

  lines[#lines + 1] = header("Project Management")
  lines[#lines + 1] = "  Tracks Branch:  " .. (def.project_mgmt.tracks_branch and "yes" or "no")
  lines[#lines + 1] = "  Worktree Iso:   " .. (def.project_mgmt.worktree_iso and "yes" or "no")
  lines[#lines + 1] = "  Session File:   " .. (def.project_mgmt.session_file and "yes" or "no")
  lines[#lines + 1] = ""

  lines[#lines + 1] = header("Detection")
  lines[#lines + 1] = "  Commands:       " .. table.concat(def.detect.cmds, ", ")
  lines[#lines + 1] = "  Title Patterns: " .. table.concat(def.detect.title_pats, ", ")
  lines[#lines + 1] = "  Strategy:       " .. def.status.strategy

  return lines
end

-- ── View: Tools (pluggable external) ──────────────────
-- External tool integration: k9s, btop, etc.
M.views.tools = function(agent)
  local lines = {}
  lines[#lines + 1] = header("External Tool Views")
  lines[#lines + 1] = ""

  -- Available tools
  local tools = {
    { name = "k9s",    cmd = "k9s",    desc = "Kubernetes cluster management",  key = "1" },
    { name = "btop",   cmd = "btop",   desc = "System resource monitor",        key = "2" },
    { name = "lazygit", cmd = "lazygit", desc = "Git TUI",                      key = "3" },
    { name = "stern",  cmd = "stern",  desc = "Kubernetes log tailing",          key = "4" },
    { name = "k9s (training)", cmd = "tc && k9s", desc = "Training cluster k9s", key = "5" },
    { name = "k9s (inference)", cmd = "ic && k9s", desc = "Inference cluster k9s", key = "6" },
  }

  lines[#lines + 1] = "  Available tools (open in new tmux pane):"
  lines[#lines + 1] = ""
  for _, tool in ipairs(tools) do
    local available = vim.fn.exepath(tool.cmd:match("^%S+")) ~= "" and "✓" or "✗"
    lines[#lines + 1] = string.format("  [%s] %s %-12s %s  %s",
      tool.key, available, tool.name, tool.desc,
      available == "✗" and "(not installed)" or "")
  end
  lines[#lines + 1] = ""
  lines[#lines + 1] = "  Press the number key to open the tool in a split pane."
  lines[#lines + 1] = ""

  -- Show fleet-specific tool panes if any exist
  lines[#lines + 1] = header("Active Tool Panes")
  local fmt = '#{session_name}\t#{pane_current_command}\t#{pane_current_path}'
  local raw = vim.fn.system("tmux list-panes -a -F '" .. fmt .. "' 2>/dev/null")
  local tool_panes = {}
  for line in raw:gmatch("[^\n]+") do
    local p = vim.split(line, "\t", { plain = true })
    if #p >= 3 then
      for _, tool in ipairs(tools) do
        if p[2] == tool.cmd:match("^%S+") then
          tool_panes[#tool_panes + 1] = { tool = tool.name, session = p[1], path = p[3] }
        end
      end
    end
  end
  if #tool_panes > 0 then
    for _, tp in ipairs(tool_panes) do
      lines[#lines + 1] = string.format("  ● %s in %s", tp.tool, tp.session)
    end
  else
    lines[#lines + 1] = "  (no tool panes active)"
  end

  -- Integration hints
  if agent then
    lines[#lines + 1] = ""
    lines[#lines + 1] = header("Context: " .. agent.project)
    lines[#lines + 1] = "  Agent: " .. agent.agent_def.icon .. " " .. agent.agent_def.label
    lines[#lines + 1] = "  Dir:   " .. agent.path
  end

  return lines
end

-- ── Tool launcher (from tools view) ───────────────────

M._tool_defs = {
  ["1"] = { cmd = "k9s", name = "k9s" },
  ["2"] = { cmd = "btop", name = "btop" },
  ["3"] = { cmd = "lazygit", name = "lazygit" },
  ["4"] = { cmd = "stern --all-namespaces", name = "stern" },
  ["5"] = { cmd = "tc && k9s", name = "k9s-training" },
  ["6"] = { cmd = "ic && k9s", name = "k9s-inference" },
}

function M.launch_tool(key, agent)
  local tool = M._tool_defs[key]
  if not tool then return end

  local dir = agent and agent.path or vim.fn.getcwd()
  local sess = vim.fn.system("tmux display-message -p '#{session_name}'"):gsub("%s+", "")

  vim.fn.system("tmux split-window -h -c " .. vim.fn.shellescape(dir))
  vim.fn.system("tmux send-keys " .. vim.fn.shellescape(tool.cmd) .. " Enter")
  vim.notify("Launched " .. tool.name, vim.log.levels.INFO)
end

-- ── View key mapping ──────────────────────────────────

M.view_keys = {
  ["<C-d>"] = "dashboard",
  ["<C-g>"] = "git",
  ["<C-m>"] = "messages",
  ["<C-p>"] = "progress",
  ["<C-i>"] = "info",
  ["<C-x>"] = "tools",
}

-- ── Main Picker ───────────────────────────────────────

function M.open(opts)
  opts = opts or {}

  local ok = pcall(require, "telescope")
  if not ok then
    vim.notify("telescope.nvim required", vim.log.levels.ERROR)
    return
  end

  local pickers    = require("telescope.pickers")
  local finders    = require("telescope.finders")
  local conf       = require("telescope.config").values
  local actions    = require("telescope.actions")
  local act_state  = require("telescope.actions.state")
  local previewers = require("telescope.previewers")

  local agents = fleet.scan({ include_git = true })
  if #agents == 0 then
    vim.notify("No agents running. Use :KhSpawn or cdev fleet spawn", vim.log.levels.INFO)
    return
  end

  -- Enrich pi agents with last message
  for _, a in ipairs(agents) do
    if a.agent_type == "pi" then
      -- Use fleet's internal helper via pane capture as fallback
      local cap = vim.fn.system(
        "tmux capture-pane -t " .. vim.fn.shellescape(a.target) .. " -p 2>/dev/null")
      local last_line = ""
      for line in cap:gmatch("[^\n]+") do
        if line:match("%S") then last_line = line end
      end
      a.last_line = last_line:sub(1, 60)
    end
  end

  -- Track current view for the preview
  local current_view_name = "pane"

  pickers.new(opts, {
    prompt_title = "🤖 Fleet Command Center (" .. #agents .. " agents)",
    results_title = "CR=jump C-s=steer C-n=new C-k=kill │ Views: C-d=dash C-g=git C-p=progress C-x=tools",

    finder = finders.new_table({
      results = agents,
      entry_maker = function(agent)
        local si = registry.status_icons[agent.status] or "?"
        local marker = agent.active and " ◀" or ""
        local git_info = ""
        if agent.git_context and agent.git_context.branch then
          local gc = agent.git_context
          if gc.changed_files > 0 then
            git_info = string.format(" [%s +%d -%d]",
              gc.branch:sub(1, 14), gc.insertions, gc.deletions)
          else
            git_info = " [" .. gc.branch:sub(1, 14) .. "]"
          end
        end

        local display = string.format("%s %s %-14s %-8s %s%s%s",
          si,
          agent.agent_def.icon,
          agent.project,
          agent.agent_type,
          agent.target,
          git_info,
          marker)

        return {
          value   = agent,
          display = display,
          ordinal = agent.project .. " " .. agent.agent_type .. " "
                      .. agent.status .. " " .. agent.session,
        }
      end,
    }),

    sorter = conf.generic_sorter(opts),

    previewer = previewers.new_buffer_previewer({
      title = "Fleet View (C-d/C-g/C-p/C-i/C-x to switch)",
      define_preview = function(self, entry)
        local view_fn = M.views[current_view_name] or M.views.pane
        local lines = view_fn(entry.value)
        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, lines)

        -- Minimal highlighting
        pcall(function()
          vim.bo[self.state.bufnr].filetype = "markdown"
        end)
      end,
    }),

    attach_mappings = function(prompt_bufnr, map)
      -- Enter: jump to agent pane
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local e = act_state.get_selected_entry()
        if e then fleet.jump(e.value.target) end
      end)

      -- View switching: each ctrl-key switches the preview panel
      for key, view_name in pairs(M.view_keys) do
        map("i", key, function()
          current_view_name = view_name
          local picker = act_state.get_current_picker(prompt_bufnr)
          if picker then picker:refresh_previewer() end
          vim.notify("View: " .. view_name, vim.log.levels.INFO)
        end)
      end

      -- Reset to pane view
      map("i", "<C-l>", function()
        current_view_name = "pane"
        local picker = act_state.get_current_picker(prompt_bufnr)
        if picker then picker:refresh_previewer() end
        vim.notify("View: pane (live)", vim.log.levels.INFO)
      end)

      -- Ctrl-s: send steering text
      map("i", "<C-s>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local agent = e.value
        actions.close(prompt_bufnr)
        vim.ui.input({
          prompt = agent.agent_def.icon .. " → " .. agent.project .. ": ",
        }, function(text)
          if text and text ~= "" then
            fleet.send(agent.target, text)
            vim.notify("Sent to " .. agent.agent_def.icon .. " " .. agent.project)
          end
        end)
      end)

      -- Ctrl-n: spawn new agent
      map("i", "<C-n>", function()
        local e = act_state.get_selected_entry()
        actions.close(prompt_bufnr)
        fleet.pick_and_spawn(e and e.value.path or vim.fn.getcwd())
      end)

      -- Ctrl-k: kill agent
      map("i", "<C-k>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        vim.fn.system("kill " .. e.value.pid)
        vim.notify("Killed: " .. e.value.agent_def.icon .. " " .. e.value.project, vim.log.levels.WARN)
        actions.close(prompt_bufnr)
        vim.defer_fn(function() M.open(opts) end, 500)
      end)

      -- Ctrl-f: send file
      map("i", "<C-f>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local file = vim.fn.expand("#:p")
        if file ~= "" then
          fleet.send(e.value.target, file)
          vim.notify("📄 → " .. e.value.agent_def.icon .. " " .. e.value.project)
        end
      end)

      -- Ctrl-r: restart with continue
      map("i", "<C-r>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local agent = e.value
        actions.close(prompt_bufnr)
        vim.fn.system("tmux send-keys -t " .. vim.fn.shellescape(agent.target) .. " C-c")
        vim.defer_fn(function()
          local cont = agent.agent_def.spawn.continue_flag
          local extra = {}
          if cont and cont ~= "" then extra[1] = cont end
          local cmd = registry.spawn_cmd(agent.agent_type, agent.path, extra)
          vim.fn.system("tmux send-keys -t " .. vim.fn.shellescape(agent.target)
            .. " " .. vim.fn.shellescape(cmd) .. " Enter")
          vim.notify("Restarted: " .. agent.agent_def.icon .. " " .. agent.project)
        end, 300)
      end)

      -- Ctrl-t: telemetry
      map("i", "<C-t>", function()
        actions.close(prompt_bufnr)
        fleet.telemetry_summary(14)
      end)

      -- Ctrl-b: broadcast to all waiting agents
      map("i", "<C-b>", function()
        actions.close(prompt_bufnr)
        local waiting = {}
        for _, a in ipairs(agents) do
          if a.status == "waiting" then waiting[#waiting + 1] = a end
        end
        if #waiting == 0 then
          vim.notify("No agents waiting for input", vim.log.levels.INFO)
          return
        end
        vim.ui.input({
          prompt = "Broadcast to " .. #waiting .. " waiting agents: ",
        }, function(text)
          if text and text ~= "" then
            for _, a in ipairs(waiting) do
              fleet.send(a.target, text)
            end
            vim.notify("Broadcast to " .. #waiting .. " agents")
          end
        end)
      end)

      -- Tool launcher keys (1-6) when in tools view
      for key_num = 1, 6 do
        map("i", tostring(key_num), function()
          if current_view_name == "tools" then
            local e = act_state.get_selected_entry()
            actions.close(prompt_bufnr)
            M.launch_tool(tostring(key_num), e and e.value or nil)
          else
            -- Pass through to telescope search in non-tools view
            vim.api.nvim_feedkeys(tostring(key_num), "n", true)
          end
        end)
      end

      return true
    end,
  }):find()
end

-- ── Setup ──────────────────────────────────────────────

function M.setup()
  vim.api.nvim_create_user_command("KhFleetTUI", function() M.open() end,
    { desc = "Fleet TUI command center" })

  vim.keymap.set("n", "<leader>dd", M.open, { desc = "Fleet: TUI command center" })
end

return M
