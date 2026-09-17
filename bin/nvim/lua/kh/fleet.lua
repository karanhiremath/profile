--- fleet.lua: Multi-agent fleet management for nvim + telescope + tmux
---
--- Scans all tmux panes for running AI coding agents (pi, claude, codex,
--- gemini, ollama, opencode), shows their status, and provides telescope
--- integration for jumping, sending text, spawning, and killing agents.
---
--- Agent types are defined in agent_registry.lua — this module consumes
--- that registry for detection, status heuristics, and spawn commands.
---
--- Commands:
---   :KhFleet          Open fleet telescope picker
---   :KhFleetSummary   Print fleet status summary
---   :KhSpawn [type] [dir]  Spawn new agent (default: pi)
---
--- Telescope mappings (inside the picker):
---   <CR>    Jump to agent pane
---   <C-s>   Send text to agent
---   <C-n>   Spawn new agent (pick type)
---   <C-k>   Kill agent
---   <C-f>   Send current file path to agent
---   <C-r>   Restart agent with continue flag
---   <C-t>   Show fleet telemetry summary
---   <C-w>   Show worktree/git changes for agent
---   <C-g>   Group view: agents by project

local M = {}

local registry = require("kh.agent_registry")

-- ── Config ─────────────────────────────────────────────

M.config = {
  session_dir   = vim.fn.expand("~/.pi/agent/sessions"),
  src_dir       = vim.fn.expand("~/src"),
  telemetry_dir = vim.fn.expand("~/.config/fleet/telemetry"),
}

-- ── Private Helpers ────────────────────────────────────

--- Strip ANSI escape sequences from captured pane text.
local function strip_ansi(s)
  s = s:gsub("\27%[[%d;]*[A-Za-z]", "")   -- CSI sequences
  s = s:gsub("\27%[%?[%d;]*[A-Za-z]", "") -- private CSI
  s = s:gsub("\27%].-\7", "")             -- OSC (BEL terminated)
  s = s:gsub("\27%].-\27\\", "")           -- OSC (ST terminated)
  s = s:gsub("\27[%(%)][ABab012]", "")     -- charset switching
  s = s:gsub("\27.", "")                   -- any remaining ESC
  return s
end

--- Encode a filesystem path to pi's session directory name.
--- /Users/foo/src/bar → --Users-foo-src-bar--
local function encode_session_path(path)
  return "--" .. path:gsub("^/", ""):gsub("/", "-") .. "--"
end

--- Read the last user message from the newest pi session file for a path.
--- Returns a short string or nil.
local function get_last_user_msg(agent_path)
  local dir = M.config.session_dir .. "/" .. encode_session_path(agent_path)

  local files = vim.fn.glob(dir .. "/*.jsonl", false, true)
  if #files == 0 then return nil end

  table.sort(files, function(a, b) return vim.fn.getftime(a) < vim.fn.getftime(b) end)
  local latest = files[#files]

  -- Read last ~120 lines, scan backwards for a user message
  local all_lines = vim.fn.readfile(latest)
  local start = math.max(1, #all_lines - 120)
  for i = #all_lines, start, -1 do
    local ok, entry = pcall(vim.fn.json_decode, all_lines[i])
    if ok and entry and entry.type == "message"
        and entry.message and entry.message.role == "user" then
      local content = entry.message.content
      if type(content) == "string" then
        return content:sub(1, 120):gsub("\n", " ")
      elseif type(content) == "table" then
        for _, block in ipairs(content) do
          if block.type == "text" then
            return block.text:sub(1, 120):gsub("\n", " ")
          end
        end
      end
    end
  end
  return nil
end

--- Get git branch and short diff stats for a working directory.
--- Returns { branch = string|nil, changed_files = number, insertions = number, deletions = number }
local function get_git_context(path)
  local ctx = { branch = nil, changed_files = 0, insertions = 0, deletions = 0 }

  local branch = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " branch --show-current 2>/dev/null")
  branch = vim.trim(branch)
  if branch ~= "" then ctx.branch = branch end

  local stat = vim.fn.system("git -C " .. vim.fn.shellescape(path) .. " diff --shortstat 2>/dev/null")
  stat = vim.trim(stat)
  if stat ~= "" then
    local files = stat:match("(%d+) file")
    local ins   = stat:match("(%d+) insertion")
    local del   = stat:match("(%d+) deletion")
    ctx.changed_files = tonumber(files) or 0
    ctx.insertions    = tonumber(ins) or 0
    ctx.deletions     = tonumber(del) or 0
  end

  return ctx
end

-- ── Telemetry ─────────────────────────────────────────

--- Record a fleet event (spawn, kill, steer, status change).
--- Events are appended to a JSONL file for later aggregation.
local function record_telemetry(event_type, data)
  local dir = M.config.telemetry_dir
  vim.fn.mkdir(dir, "p")

  local event = vim.tbl_extend("force", {
    ts         = os.date("!%Y-%m-%dT%H:%M:%SZ"),
    event      = event_type,
    registry_v = registry.VERSION,
  }, data or {})

  local path = dir .. "/" .. os.date("%Y-%m-%d") .. ".jsonl"
  local f = io.open(path, "a")
  if f then
    f:write(vim.fn.json_encode(event) .. "\n")
    f:close()
  end
end

--- Aggregate telemetry from recent files.
--- Returns { total_events, by_type = {}, by_agent = {}, by_project = {},
---           avg_wait_seconds = number, busiest_project = string }
function M.aggregate_telemetry(days)
  days = days or 7
  local dir = M.config.telemetry_dir
  local results = {
    total_events    = 0,
    by_event        = {},
    by_agent_type   = {},
    by_project      = {},
    wait_times      = {},
    spawn_count     = 0,
    steer_count     = 0,
    kill_count       = 0,
  }

  local now = os.time()
  for d = 0, days - 1 do
    local date_str = os.date("%Y-%m-%d", now - d * 86400)
    local path = dir .. "/" .. date_str .. ".jsonl"
    local f = io.open(path, "r")
    if f then
      for line in f:lines() do
        local ok, event = pcall(vim.fn.json_decode, line)
        if ok and event then
          results.total_events = results.total_events + 1

          local et = event.event or "unknown"
          results.by_event[et] = (results.by_event[et] or 0) + 1

          if event.agent_type then
            results.by_agent_type[event.agent_type] =
              (results.by_agent_type[event.agent_type] or 0) + 1
          end
          if event.project then
            results.by_project[event.project] =
              (results.by_project[event.project] or 0) + 1
          end

          if et == "spawn" then results.spawn_count = results.spawn_count + 1 end
          if et == "steer" then results.steer_count = results.steer_count + 1 end
          if et == "kill"  then results.kill_count  = results.kill_count + 1 end

          if event.wait_seconds then
            results.wait_times[#results.wait_times + 1] = event.wait_seconds
          end
        end
      end
      f:close()
    end
  end

  -- Compute averages
  if #results.wait_times > 0 then
    local sum = 0
    for _, w in ipairs(results.wait_times) do sum = sum + w end
    results.avg_wait_seconds = sum / #results.wait_times
  end

  -- Find busiest project
  local max_count, busiest = 0, nil
  for proj, count in pairs(results.by_project) do
    if count > max_count then max_count = count; busiest = proj end
  end
  results.busiest_project = busiest

  return results
end

--- Generate optimization proposals from telemetry data.
function M.propose_optimizations(days)
  local stats = M.aggregate_telemetry(days or 14)
  local proposals = {}

  -- High wait time → suggest more autonomous agent config
  if stats.avg_wait_seconds and stats.avg_wait_seconds > 120 then
    proposals[#proposals + 1] = {
      severity = "high",
      area     = "wait_time",
      message  = string.format(
        "Avg agent wait time is %.0fs. Consider pre-loading context or using continue flags to reduce human handoff latency.",
        stats.avg_wait_seconds),
    }
  end

  -- Imbalanced agent type usage → suggest trying underused agents
  local type_counts = {}
  for _, at in ipairs(registry.order) do
    type_counts[#type_counts + 1] = { type = at, count = stats.by_agent_type[at] or 0 }
  end
  table.sort(type_counts, function(a, b) return a.count > b.count end)
  if #type_counts >= 2 and type_counts[1].count > 0 then
    local top = type_counts[1]
    local ratio = top.count / math.max(stats.total_events, 1)
    if ratio > 0.8 then
      proposals[#proposals + 1] = {
        severity = "medium",
        area     = "agent_diversity",
        message  = string.format(
          "%s accounts for %.0f%% of fleet activity. Consider distributing work across agent types for resilience.",
          registry.agents[top.type].label, ratio * 100),
      }
    end
  end

  -- High spawn/kill churn → suggest session persistence
  if stats.spawn_count > 20 and stats.kill_count > 15 then
    local churn_ratio = stats.kill_count / stats.spawn_count
    if churn_ratio > 0.6 then
      proposals[#proposals + 1] = {
        severity = "medium",
        area     = "session_churn",
        message  = string.format(
          "%.0f%% of spawned agents get killed. Use continue/resume flags to persist sessions instead of respawning.",
          churn_ratio * 100),
      }
    end
  end

  -- Project concentration → suggest parallelization
  if stats.busiest_project and stats.by_project[stats.busiest_project] then
    local proj_ratio = stats.by_project[stats.busiest_project] / math.max(stats.total_events, 1)
    if proj_ratio > 0.5 and vim.tbl_count(stats.by_project) > 1 then
      proposals[#proposals + 1] = {
        severity = "low",
        area     = "project_balance",
        message  = string.format(
          "'%s' dominates fleet activity (%.0f%%). Other projects may be starved — check their backlog.",
          stats.busiest_project, proj_ratio * 100),
      }
    end
  end

  return proposals, stats
end

-- ── Status Detection ───────────────────────────────────

--- Generic status detection from captured pane text using agent-specific patterns.
function M._detect_status(capture, agent_def)
  if not capture or capture == "" then return "unknown" end

  local clean = capture:find("\27") and strip_ansi(capture) or capture

  local lines = {}
  for line in clean:gmatch("([^\n]*)") do
    lines[#lines + 1] = line
  end
  if #lines == 0 then return "unknown" end

  -- Look at the last 20 lines for signals
  local tail_start = math.max(1, #lines - 20)
  local tail = table.concat(vim.list_slice(lines, tail_start, #lines), "\n")

  local status_cfg = agent_def and agent_def.status or {}

  -- Working: check working patterns
  local working_pats = status_cfg.working_pats or {}
  for _, pat in ipairs(working_pats) do
    -- Try as plain string first (for spinner chars), then as pattern
    if tail:find(pat, 1, true) or tail:match(pat) then
      return "working"
    end
  end

  -- Waiting: check waiting patterns
  local waiting_pats = status_cfg.waiting_pats or {}
  for _, pat in ipairs(waiting_pats) do
    if tail:find(pat, 1, true) or tail:match(pat) then
      return "waiting"
    end
  end

  return "idle"
end

-- ── Scanning ───────────────────────────────────────────

--- Scan all tmux panes and return a sorted list of agents across all types.
--- Each entry: { target, session, window, win_idx, pane, pid, title,
---               path, project, status, active, agent_type, agent_def,
---               git_context }
function M.scan(opts)
  opts = opts or {}
  local include_git = opts.include_git or false

  local fmt = table.concat({
    "#{session_name}",  "#{window_name}", "#{window_index}",
    "#{pane_index}",    "#{pane_pid}",    "#{pane_current_command}",
    "#{pane_title}",    "#{pane_current_path}",
    "#{pane_active}",   "#{window_active}","#{session_attached}",
  }, "\t")

  local raw = vim.fn.system("tmux list-panes -a -F '" .. fmt .. "' 2>/dev/null")
  local agents = {}

  for line in raw:gmatch("[^\n]+") do
    local p = vim.split(line, "\t", { plain = true })
    if #p >= 11 then
      local cmd, title = p[6], p[7]

      -- Match against all registered agent types
      local agent_def = registry.match_pane(cmd, title)
      if agent_def then
        local target = p[1] .. ":" .. p[3] .. "." .. p[4]
        local path   = p[8]
        local project = path:match("/src/([^/]+)$")
                     or path:match("/([^/]+)$")
                     or "~"

        -- Detect status
        local status
        if agent_def.type == "pi" and title:match("^✳") then
          status = "init"
        else
          local cap = vim.fn.system(
            "tmux capture-pane -t " .. vim.fn.shellescape(target) .. " -p 2>/dev/null")
          status = M._detect_status(cap, agent_def)
        end

        -- Optionally gather git context
        local git_ctx = nil
        if include_git then
          git_ctx = get_git_context(path)
        end

        agents[#agents + 1] = {
          target     = target,
          session    = p[1],
          window     = p[2],
          win_idx    = p[3],
          pane       = p[4],
          pid        = p[5],
          title      = title,
          path       = path,
          project    = project,
          status     = status,
          active     = p[9] == "1" and p[10] == "1" and p[11] ~= "0",
          agent_type = agent_def.type,
          agent_def  = agent_def,
          git_context = git_ctx,
        }
      end
    end
  end

  -- Sort: waiting first (needs attention), then working, then rest
  -- Within same status, group by project
  local pri = { waiting = 1, working = 2, init = 3, idle = 4, unknown = 5 }
  table.sort(agents, function(a, b)
    local pa, pb = pri[a.status] or 9, pri[b.status] or 9
    if pa ~= pb then return pa < pb end
    if a.project ~= b.project then return a.project < b.project end
    return a.agent_type < b.agent_type
  end)

  return agents
end

-- ── Actions ────────────────────────────────────────────

--- Jump to a tmux pane target (session:window.pane).
function M.jump(target)
  local tgt_sess = target:match("^([^:]+)")
  local cur_sess = vim.fn.system("tmux display-message -p '#{session_name}'"):gsub("%s+", "")
  if cur_sess ~= tgt_sess then
    vim.fn.system("tmux switch-client -t " .. vim.fn.shellescape(tgt_sess))
  end
  vim.fn.system("tmux select-window -t " .. vim.fn.shellescape(target))
  vim.fn.system("tmux select-pane -t "   .. vim.fn.shellescape(target))
end

--- Send text followed by Enter to a pane.
function M.send(target, text)
  vim.fn.system("tmux send-keys -t " .. vim.fn.shellescape(target)
    .. " " .. vim.fn.shellescape(text) .. " Enter")
end

--- Spawn a new agent.
--- opts.dir        — working directory (default: cwd)
--- opts.split      — "window" (default), "hsplit", "vsplit"
--- opts.agent_type — registry key (default: "pi")
--- opts.extra_args — extra args for the agent
function M.spawn(opts)
  opts = opts or {}
  local dir        = opts.dir or vim.fn.getcwd()
  local split      = opts.split or "window"
  local agent_type = opts.agent_type or "pi"
  local extra_args = opts.extra_args

  local agent_def = registry.get(agent_type)
  if not agent_def then
    vim.notify("Unknown agent type: " .. agent_type, vim.log.levels.ERROR)
    return
  end

  local spawn_cmd = registry.spawn_cmd(agent_type, dir, extra_args)
  if not spawn_cmd then
    vim.notify("Cannot build spawn command for: " .. agent_type, vim.log.levels.ERROR)
    return
  end

  local sess    = vim.fn.system("tmux display-message -p '#{session_name}'"):gsub("%s+", "")
  local project = dir:match("/([^/]+)$") or "agent"
  local win_name = agent_def.icon .. ":" .. project

  if split == "hsplit" then
    vim.fn.system("tmux split-window -h -c " .. vim.fn.shellescape(dir))
  elseif split == "vsplit" then
    vim.fn.system("tmux split-window -v -c " .. vim.fn.shellescape(dir))
  else
    vim.fn.system("tmux new-window -t " .. vim.fn.shellescape(sess)
      .. " -n " .. vim.fn.shellescape(win_name)
      .. " -c " .. vim.fn.shellescape(dir))
  end
  vim.fn.system("tmux send-keys " .. vim.fn.shellescape(spawn_cmd) .. " Enter")

  record_telemetry("spawn", {
    agent_type = agent_type,
    project    = project,
    dir        = dir,
    split      = split,
  })

  vim.notify("⚡ Spawned " .. agent_def.label .. " → " .. project, vim.log.levels.INFO)
end

-- ── Summary ────────────────────────────────────────────

function M.summary()
  local agents = M.scan()
  if #agents == 0 then
    print("No agents running.")
    return
  end

  -- Count by type and status
  local by_type = {}
  local by_proj = {}
  local counts  = { waiting = 0, working = 0, init = 0, idle = 0, unknown = 0 }
  for _, a in ipairs(agents) do
    by_type[a.agent_type] = (by_type[a.agent_type] or 0) + 1
    by_proj[a.project]    = by_proj[a.project] or {}
    table.insert(by_proj[a.project], a)
    counts[a.status] = (counts[a.status] or 0) + 1
  end

  -- Header
  print(string.format(
    "🤖 Fleet: %d agents  ⏳%d waiting  ⚙️ %d working  ✳%d init  💤%d idle",
    #agents, counts.waiting, counts.working, counts.init, counts.idle))

  -- Type breakdown
  local type_parts = {}
  for _, key in ipairs(registry.order) do
    local count = by_type[key]
    if count then
      local def = registry.get(key)
      type_parts[#type_parts + 1] = def.icon .. " " .. def.label .. ":" .. count
    end
  end
  if #type_parts > 0 then
    print("  Types: " .. table.concat(type_parts, "  "))
  end

  print(string.rep("─", 68))

  -- Sort projects by count descending
  local projects = vim.tbl_keys(by_proj)
  table.sort(projects, function(a, b) return #by_proj[a] > #by_proj[b] end)
  for _, proj in ipairs(projects) do
    local icons = {}
    for _, a in ipairs(by_proj[proj]) do
      local si = registry.status_icons[a.status] or "?"
      local ai = a.agent_def.icon
      icons[#icons + 1] = ai .. si
    end
    print(string.format("  %-24s %s", proj, table.concat(icons, " ")))
  end
end

--- Print telemetry summary and optimization proposals.
function M.telemetry_summary(days)
  local proposals, stats = M.propose_optimizations(days or 14)

  print(string.format("📊 Fleet Telemetry (%dd)", days or 14))
  print(string.rep("─", 52))
  print(string.format("  Events: %d total  |  Spawns: %d  Steers: %d  Kills: %d",
    stats.total_events, stats.spawn_count, stats.steer_count, stats.kill_count))

  if stats.avg_wait_seconds then
    print(string.format("  Avg wait: %.0fs", stats.avg_wait_seconds))
  end

  -- Agent type breakdown
  local parts = {}
  for _, key in ipairs(registry.order) do
    local count = stats.by_agent_type[key]
    if count and count > 0 then
      parts[#parts + 1] = registry.agents[key].icon .. ":" .. count
    end
  end
  if #parts > 0 then
    print("  By type: " .. table.concat(parts, "  "))
  end

  -- Proposals
  if #proposals > 0 then
    print("")
    print("💡 Optimization Proposals:")
    for _, p in ipairs(proposals) do
      local sev_icon = p.severity == "high" and "🔴" or (p.severity == "medium" and "🟡" or "🔵")
      print(string.format("  %s [%s] %s", sev_icon, p.area, p.message))
    end
  else
    print("  ✅ No optimization issues detected.")
  end
end

-- ── Telescope Picker ───────────────────────────────────

function M.pick(opts)
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

  local agents = M.scan({ include_git = true })
  if #agents == 0 then
    vim.notify("No agents running", vim.log.levels.INFO)
    return
  end

  -- Enrich pi agents with last user message (best-effort)
  for _, a in ipairs(agents) do
    if a.agent_type == "pi" then
      a.last_msg = get_last_user_msg(a.path)
    end
  end

  pickers.new(opts, {
    prompt_title = "🤖 Agent Fleet (" .. #agents .. ")",
    results_title = "⏳=wait ⚙️=work ✳=init 💤=idle │ <C-s>send <C-n>new <C-k>kill <C-t>telemetry",

    finder = finders.new_table({
      results = agents,
      entry_maker = function(agent)
        local si     = registry.status_icons[agent.status] or "?"
        local marker = agent.active and " ◀" or ""
        local msg    = agent.last_msg
                         and ("  │ " .. agent.last_msg:sub(1, 40))
                         or ""
        local git_info = ""
        if agent.git_context and agent.git_context.branch then
          local gc = agent.git_context
          git_info = string.format(" [%s +%d -%d]",
            gc.branch:sub(1, 16), gc.insertions, gc.deletions)
        end

        local display = string.format("%s %s %-14s %-10s [%s.%s]%s%s%s",
          si,
          agent.agent_def.icon,
          agent.project,
          agent.title:gsub("^π %- ", ""):sub(1, 10),
          agent.session, agent.pane,
          git_info, marker, msg)

        return {
          value   = agent,
          display = display,
          ordinal = agent.project .. " " .. agent.agent_type .. " "
                      .. agent.session .. " " .. agent.status
                      .. " " .. (agent.last_msg or ""),
        }
      end,
    }),

    sorter = conf.generic_sorter(opts),

    previewer = previewers.new_termopen_previewer({
      title = "Pane Preview",
      get_command = function(entry)
        return { "tmux", "capture-pane", "-t", entry.value.target, "-p", "-e" }
      end,
    }),

    attach_mappings = function(prompt_bufnr, map)
      -- Enter: jump to agent pane
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local e = act_state.get_selected_entry()
        if e then
          M.jump(e.value.target)
          record_telemetry("jump", {
            agent_type = e.value.agent_type,
            project    = e.value.project,
          })
        end
      end)

      -- Ctrl-s: send text to agent
      map("i", "<C-s>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local agent = e.value
        actions.close(prompt_bufnr)
        vim.ui.input({
          prompt = agent.agent_def.icon .. " → " .. agent.project .. ": ",
        }, function(text)
          if text and text ~= "" then
            M.send(agent.target, text)
            record_telemetry("steer", {
              agent_type = agent.agent_type,
              project    = agent.project,
              msg_len    = #text,
            })
            vim.notify("Sent to " .. agent.agent_def.icon .. " " .. agent.project)
          end
        end)
      end)

      -- Ctrl-n: spawn new agent (pick type)
      map("i", "<C-n>", function()
        local e = act_state.get_selected_entry()
        actions.close(prompt_bufnr)
        local dir = e and e.value.path or vim.fn.getcwd()
        M.pick_and_spawn(dir)
      end)

      -- Ctrl-k: kill agent
      map("i", "<C-k>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local agent = e.value
        vim.fn.system("kill " .. agent.pid)
        record_telemetry("kill", {
          agent_type = agent.agent_type,
          project    = agent.project,
        })
        vim.notify("Killed: " .. agent.agent_def.icon .. " " .. agent.project, vim.log.levels.WARN)
        actions.close(prompt_bufnr)
        vim.defer_fn(function() M.pick(opts) end, 500)
      end)

      -- Ctrl-f: send current file to agent
      map("i", "<C-f>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local file = vim.fn.expand("#:p") -- file before telescope opened
        if file == "" then
          vim.notify("No file to send", vim.log.levels.WARN)
          return
        end
        M.send(e.value.target, file)
        vim.notify("📄 → " .. e.value.agent_def.icon .. " " .. e.value.project)
      end)

      -- Ctrl-r: restart agent with continue flag
      map("i", "<C-r>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local agent = e.value
        actions.close(prompt_bufnr)
        -- Send Ctrl-C to stop current process, then relaunch
        vim.fn.system("tmux send-keys -t " .. vim.fn.shellescape(agent.target) .. " C-c")
        vim.defer_fn(function()
          local cont_flag = agent.agent_def.spawn.continue_flag
          local extra = {}
          if cont_flag and cont_flag ~= "" then
            extra[1] = cont_flag
          end
          local cmd = registry.spawn_cmd(agent.agent_type, agent.path, extra)
          vim.fn.system("tmux send-keys -t " .. vim.fn.shellescape(agent.target)
            .. " " .. vim.fn.shellescape(cmd) .. " Enter")
          record_telemetry("restart", {
            agent_type = agent.agent_type,
            project    = agent.project,
            continued  = cont_flag ~= "",
          })
          vim.notify("Restarted: " .. agent.agent_def.icon .. " " .. agent.project
            .. (cont_flag ~= "" and " (" .. cont_flag .. ")" or ""))
        end, 300)
      end)

      -- Ctrl-t: telemetry summary
      map("i", "<C-t>", function()
        actions.close(prompt_bufnr)
        M.telemetry_summary(14)
      end)

      -- Ctrl-w: show git changes for selected agent
      map("i", "<C-w>", function()
        local e = act_state.get_selected_entry()
        if not e then return end
        local agent = e.value
        actions.close(prompt_bufnr)
        local diff = vim.fn.system("git -C " .. vim.fn.shellescape(agent.path)
          .. " diff --stat 2>/dev/null")
        if vim.trim(diff) == "" then
          vim.notify(agent.agent_def.icon .. " " .. agent.project .. ": no changes", vim.log.levels.INFO)
        else
          -- Open in a scratch buffer
          vim.cmd("vnew")
          vim.bo.buftype = "nofile"
          vim.bo.bufhidden = "wipe"
          vim.bo.filetype = "diff"
          local buf_name = agent.agent_def.icon .. " " .. agent.project .. " changes"
          vim.api.nvim_buf_set_name(0, buf_name)
          -- Get full diff
          local full = vim.fn.system("git -C " .. vim.fn.shellescape(agent.path)
            .. " diff 2>/dev/null")
          vim.api.nvim_buf_set_lines(0, 0, -1, false, vim.split(full, "\n"))
        end
      end)

      -- Ctrl-g: group by project
      map("i", "<C-g>", function()
        actions.close(prompt_bufnr)
        M.summary()
      end)

      return true
    end,
  }):find()
end

--- Interactive agent type picker, then spawn.
function M.pick_and_spawn(dir)
  dir = dir or vim.fn.getcwd()
  local available = registry.available()

  if #available == 0 then
    vim.notify("No agent binaries found on PATH", vim.log.levels.ERROR)
    return
  end

  if #available == 1 then
    M.spawn({ dir = dir, agent_type = available[1].type })
    return
  end

  local items = {}
  for _, agent in ipairs(available) do
    items[#items + 1] = agent.icon .. "  " .. agent.label
  end

  vim.ui.select(items, {
    prompt = "Spawn agent in " .. (dir:match("/([^/]+)$") or dir) .. ":",
  }, function(_, idx)
    if idx then
      M.spawn({ dir = dir, agent_type = available[idx].type })
    end
  end)
end

-- ── Setup ──────────────────────────────────────────────

function M.setup()
  vim.api.nvim_create_user_command("KhFleet", function() M.pick() end,
    { desc = "Agent fleet picker" })
  vim.api.nvim_create_user_command("KhFleetSummary", function() M.summary() end,
    { desc = "Fleet summary" })
  vim.api.nvim_create_user_command("KhFleetTelemetry", function(cmd)
    local days = tonumber(cmd.fargs[1]) or 14
    M.telemetry_summary(days)
  end, { nargs = "?", desc = "Fleet telemetry" })
  vim.api.nvim_create_user_command("KhSpawn", function(cmd)
    local agent_type = cmd.fargs[1] or nil
    local dir = cmd.fargs[2] or vim.fn.getcwd()
    if agent_type then
      M.spawn({ dir = dir, agent_type = agent_type })
    else
      M.pick_and_spawn(dir)
    end
  end, { nargs = "*", desc = "Spawn agent", complete = function()
    local types = {}
    for _, key in ipairs(registry.order) do types[#types + 1] = key end
    return types
  end })

  -- Export registry for CLI tools on setup
  registry.export()

  -- Leader mappings
  vim.keymap.set("n", "<leader>ca", M.pick, { desc = "Fleet: agent picker" })
  vim.keymap.set("n", "<leader>ds", M.summary, { desc = "Fleet: summary" })
  vim.keymap.set("n", "<leader>dt", function() M.telemetry_summary(14) end,
    { desc = "Fleet: telemetry" })
end

return M
