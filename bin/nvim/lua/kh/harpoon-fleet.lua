--- harpoon-fleet.lua: Named quick-navigation for the multi-agent fleet.
---
--- Binds <C-h> as a prefix key for instant fleet navigation across all
--- agent types (pi, claude, codex, gemini, ollama, opencode).
---
---   <C-h>1-9       Jump to fleet agent by scan index
---   <C-h><C-h>     Fleet quick menu (vim.ui.select)
---   <C-h>a         Fleet telescope picker (full view)
---   <C-h>n         Spawn new agent (pick type)
---   <C-h>o         Optimization proposals from telemetry
---
---   <C-h>b         → bifrost         <C-h>g → gypsum
---   <C-h>c         → compliance      <C-h>p → product
---   <C-h>f         → profile         <C-h>k → karan.hiremath
---   <C-h>t         → tcloud          <C-h>s → csec
---   <C-h>i         → fips            <C-h>x → patching
---
---   <C-h>d         Datadog incidents  (stub)
---   <C-h>l         Linear tasks       (stub)
---   <C-h>h         Host picker
---   <C-h>r         Cluster picker

local M = {}

local registry = require("kh.agent_registry")

-- ── Project Shortcuts ──────────────────────────────────
-- key → { name (display), patterns (match against agent.project),
--          preferred_agent (optional: default agent type for this project) }

M.shortcuts = {
  b = { name = "bifrost",        patterns = { "bifrost" },                        preferred_agent = "pi" },
  c = { name = "compliance",     patterns = { "compliance", "cartesia%-security" }, preferred_agent = "pi" },
  g = { name = "gypsum",         patterns = { "gypsum" },                         preferred_agent = "pi" },
  p = { name = "product",        patterns = { "product" },                        preferred_agent = "pi" },
  f = { name = "profile",        patterns = { "^profile$" },                      preferred_agent = "claude" },
  k = { name = "karan.hiremath", patterns = { "karan%.hiremath", "karan%-hiremath" }, preferred_agent = "claude" },
  t = { name = "tcloud",         patterns = { "tcloud" },                         preferred_agent = "pi" },
  s = { name = "csec",           patterns = { "csec" },                           preferred_agent = "pi" },
  i = { name = "fips",           patterns = { "fips" },                           preferred_agent = "pi" },
  x = { name = "patching",       patterns = { "patching", "csec%-patch" },        preferred_agent = "pi" },
}

-- ── Core ───────────────────────────────────────────────

--- Find the first running agent whose project matches any of `patterns`.
--- Prefers "waiting" agents, then "working", then anything.
--- If `agent_type` is specified, only matches that type.
local function find_agent(patterns, agent_type)
  local fleet  = require("kh.fleet")
  local agents = fleet.scan() -- already sorted: waiting first

  for _, agent in ipairs(agents) do
    if not agent_type or agent.agent_type == agent_type then
      for _, pat in ipairs(patterns) do
        if agent.project:lower():match(pat:lower()) then
          return agent
        end
      end
    end
  end
  return nil
end

--- Find ALL running agents matching patterns (for multi-agent project view).
local function find_all_agents(patterns)
  local fleet  = require("kh.fleet")
  local agents = fleet.scan()
  local matches = {}

  for _, agent in ipairs(agents) do
    for _, pat in ipairs(patterns) do
      if agent.project:lower():match(pat:lower()) then
        matches[#matches + 1] = agent
        break
      end
    end
  end
  return matches
end

--- Jump to the agent for a named shortcut key.
--- If multiple agents exist for the project, shows a picker.
function M.jump_shortcut(key)
  local sc = M.shortcuts[key]
  if not sc then
    vim.notify("No fleet shortcut: " .. key, vim.log.levels.WARN)
    return
  end

  local all = find_all_agents(sc.patterns)

  if #all == 0 then
    -- No running agent — offer to spawn with type selection
    M._offer_spawn(sc)
  elseif #all == 1 then
    -- Single agent — jump directly
    local agent = all[1]
    require("kh.fleet").jump(agent.target)
    vim.notify(agent.agent_def.icon .. " " .. sc.name .. " " .. (registry.status_icons[agent.status] or ""))
  else
    -- Multiple agents on this project — pick which one
    local items = {}
    local lookup = {}
    for _, a in ipairs(all) do
      items[#items + 1] = string.format("%s %s  %s  [%s.%s]",
        a.agent_def.icon,
        registry.status_icons[a.status] or "?",
        a.agent_type,
        a.session, a.pane)
      lookup[#items] = a
    end

    vim.ui.select(items, {
      prompt = sc.name .. " — " .. #all .. " agents:",
    }, function(_, idx)
      if idx and lookup[idx] then
        require("kh.fleet").jump(lookup[idx].target)
      end
    end)
  end
end

--- Offer to spawn a new agent with type selection.
function M._offer_spawn(sc)
  local available = registry.available()
  if #available == 0 then
    vim.notify("No agent binaries found on PATH", vim.log.levels.ERROR)
    return
  end

  -- If preferred agent is available, put it first
  local preferred = sc.preferred_agent
  local ordered = {}
  for _, a in ipairs(available) do
    if a.type == preferred then
      table.insert(ordered, 1, a)
    else
      ordered[#ordered + 1] = a
    end
  end

  local items = {}
  for _, a in ipairs(ordered) do
    local default_marker = a.type == preferred and " (default)" or ""
    items[#items + 1] = a.icon .. "  " .. a.label .. default_marker
  end

  -- Add cancel option
  items[#items + 1] = "   Cancel"

  vim.ui.select(items, {
    prompt = "No " .. sc.name .. " agent — spawn:",
  }, function(_, idx)
    if idx and idx <= #ordered then
      local dir = vim.fn.expand("~/src/" .. sc.name)
      if vim.fn.isdirectory(dir) == 1 then
        require("kh.fleet").spawn({
          dir = dir,
          agent_type = ordered[idx].type,
        })
      else
        vim.notify("Dir not found: " .. dir, vim.log.levels.ERROR)
      end
    end
  end)
end

--- Jump to the Nth agent from the fleet scan (1-indexed).
function M.jump_index(idx)
  local fleet  = require("kh.fleet")
  local agents = fleet.scan()

  if idx > #agents then
    vim.notify(string.format("Fleet [%d]: only %d agents running", idx, #agents),
      vim.log.levels.WARN)
    return
  end

  local a = agents[idx]
  fleet.jump(a.target)
  vim.notify(string.format("[%d] %s %s %s",
    idx, a.agent_def.icon, a.project, registry.status_icons[a.status] or ""))
end

--- Quick menu: numbered agents with type icons and shortcut hints.
function M.menu()
  local fleet  = require("kh.fleet")
  local agents = fleet.scan()

  if #agents == 0 then
    vim.notify("No agents running", vim.log.levels.INFO)
    return
  end

  local items  = {}
  local lookup = {}

  -- Build reverse map: project → shortcut key
  local proj_to_key = {}
  for key, sc in pairs(M.shortcuts) do
    for _, pat in ipairs(sc.patterns) do
      proj_to_key[pat] = key
    end
  end

  local function shortcut_for(project)
    for pat, key in pairs(proj_to_key) do
      if project:lower():match(pat:lower()) then return key end
    end
    return ""
  end

  for i, a in ipairs(agents) do
    if i > 15 then
      items[#items + 1] = string.format("  … and %d more  →  :KhFleet", #agents - 15)
      break
    end
    local sc  = shortcut_for(a.project)
    local num = i <= 9 and tostring(i) or " "
    items[#items + 1] = string.format("%s %s %s %-16s %s  [%s]%s",
      num,
      a.agent_def.icon,
      registry.status_icons[a.status] or "?",
      a.project,
      sc ~= "" and ("C-h " .. sc) or "      ",
      a.session,
      a.active and " ◀" or "")
    lookup[#items] = a
  end

  vim.ui.select(items, {
    prompt = "🤖 Fleet (" .. #agents .. " agents):",
    format_item = function(item) return item end,
  }, function(_, idx)
    if idx and lookup[idx] then
      fleet.jump(lookup[idx].target)
    end
  end)
end

-- ── Service Integration Stubs ──────────────────────────

function M.linear_tasks()
  vim.notify("📋 Linear: set LINEAR_API_KEY to enable", vim.log.levels.INFO)
end

function M.datadog_incidents()
  vim.notify("🐕 Datadog: set DD_API_KEY + DD_APP_KEY to enable", vim.log.levels.INFO)
end

--- Pick a host from karan.hiremath/scripts/hosts.conf and open a tmux split.
function M.host_picker()
  local conf_path = vim.fn.expand("~/src/karan.hiremath/scripts/hosts.conf")
  if vim.fn.filereadable(conf_path) == 0 then
    vim.notify("hosts.conf not found", vim.log.levels.WARN)
    return
  end

  local hosts = {}
  for _, line in ipairs(vim.fn.readfile(conf_path)) do
    if not line:match("^#") and line:match("%S") then
      local name = vim.trim(line:match("^([^|]+)") or "")
      if name ~= "" then hosts[#hosts + 1] = name end
    end
  end

  if #hosts == 0 then
    vim.notify("No hosts in hosts.conf", vim.log.levels.WARN)
    return
  end

  vim.ui.select(hosts, { prompt = "🖥️  Connect to host:" }, function(choice)
    if choice then
      local tc = vim.fn.expand("~/src/profile/bin/tmux/tmux-connect")
      vim.fn.system("tmux split-window -h '" .. tc .. " " .. choice .. "'")
    end
  end)
end

--- Pick a cluster and open a tmux split with tc/ic.
function M.cluster_picker()
  local clusters = {
    { name = "Training: default",  cmd = "tc" },
    { name = "Training: Together", cmd = "tc tg" },
    { name = "Inference: TG",      cmd = "ic tg" },
    { name = "Inference: Staging", cmd = "ic staging" },
    { name = "Inference: US-West", cmd = "ic us" },
    { name = "Inference: EU",      cmd = "ic eu" },
    { name = "Inference: UK",      cmd = "ic uk" },
    { name = "Inference: AP",      cmd = "ic ap" },
    { name = "Inference: AU",      cmd = "ic au" },
  }

  vim.ui.select(
    vim.tbl_map(function(c) return c.name end, clusters),
    { prompt = "☁️  Cluster:" },
    function(_, idx)
      if idx then
        vim.fn.system("tmux split-window -h '" .. clusters[idx].cmd .. "'")
      end
    end)
end

-- ── Optimization proposals shortcut ───────────────────

function M.show_optimizations()
  require("kh.fleet").telemetry_summary(14)
end

-- ── Setup (keybindings) ────────────────────────────────

function M.setup()
  local nmap = function(lhs, rhs, desc)
    vim.keymap.set("n", lhs, rhs, { noremap = true, silent = true, desc = desc })
  end

  -- ── <C-h> prefix: numbered fleet slots ───────────────
  for i = 1, 9 do
    nmap("<C-h>" .. i, function() M.jump_index(i) end, "Fleet: agent " .. i)
  end

  -- ── <C-h> prefix: fleet menu / picker ────────────────
  nmap("<C-h><C-h>", M.menu,                                    "Fleet: quick menu")
  nmap("<C-h>a",     function() require("kh.fleet").pick() end, "Fleet: telescope picker")
  nmap("<C-h>n",     function()
    require("kh.fleet").pick_and_spawn()
  end, "Fleet: spawn agent (pick type)")
  nmap("<C-h>o", M.show_optimizations, "Fleet: optimization proposals")

  -- ── <C-h> prefix: project shortcuts ──────────────────
  for key, sc in pairs(M.shortcuts) do
    nmap("<C-h>" .. key, function() M.jump_shortcut(key) end, "Fleet: " .. sc.name)
  end

  -- ── <C-h> prefix: services / infra ──────────────────
  nmap("<C-h>l", M.linear_tasks,     "Fleet: Linear tasks")
  nmap("<C-h>d", M.datadog_incidents, "Fleet: Datadog incidents")
  nmap("<C-h>h", M.host_picker,      "Fleet: host picker")
  nmap("<C-h>r", M.cluster_picker,   "Fleet: cluster picker")
end

return M
