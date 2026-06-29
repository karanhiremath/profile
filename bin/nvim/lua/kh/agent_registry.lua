--- agent_registry.lua: Shared agent type definitions for fleet management.
local M = {}

M.VERSION = "1.1.0"

M.agents = {
  pi = {
    type  = "pi",
    label = "Pi Coding Agent",
    icon  = "π",
    color = "magenta",
    detect = { cmds = { "node" }, title_pats = { "^π", "^✳", "^pi:" }, path_hints = { "pi" } },
    spawn = { cmd = "pi", default_args = {}, continue_flag = "-c", project_flag = nil },
    session = { dir = "~/.pi/agent/sessions", file_pattern = "*.jsonl" },
    status = {
      strategy = "tui_capture",
      working_pats = { "Working", "Running", "Executing" },
      waiting_pats = { "%$%d+%.%d+", "↑%d", "↓%d" },
    },
    project_mgmt = { tracks_branch = true, worktree_iso = false, session_file = true },
  },

  cursor = {
    type  = "cursor",
    label = "Cursor Agent",
    icon  = "◆",
    color = "cyan",
    detect = {
      cmds       = { "cursor-agent", "agent" },
      title_pats = { "cursor", "Cursor", "Composer" },
      path_hints = { "cursor-agent", "agent" },
    },
    spawn = {
      cmd           = "cursor-agent",
      default_args  = { "--model", "claude-opus-4-8-thinking-high" },
      continue_flag = "--continue",
      project_flag  = "--workspace",
    },
    session = {
      dir          = "~/.cursor/projects",
      file_pattern = "**/agent-transcripts/**/*.jsonl",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "Thinking", "Running", "Executing", "Working" },
      waiting_pats = { "^>", "❯" },
    },
    project_mgmt = { tracks_branch = true, worktree_iso = true, session_file = true },
  },

  claude = {
    type  = "claude",
    label = "Claude Code",
    icon  = "C",
    color = "cyan",
    detect = { cmds = { "claude" }, title_pats = { "claude", "Claude" }, path_hints = { "claude" } },
    spawn = { cmd = "claude", default_args = {}, continue_flag = "--continue", project_flag = nil },
    session = { dir = "~/.claude/projects", file_pattern = "*.json" },
    status = {
      strategy = "tui_capture",
      working_pats = { "Thinking", "Reading", "Editing", "Running", "Searching", "Writing", "Creating" },
      waiting_pats = { "^>", "^❯", "What would you like" },
    },
    project_mgmt = { tracks_branch = true, worktree_iso = true, session_file = true },
  },

  codex = {
    type  = "codex",
    label = "Codex CLI",
    icon  = "X",
    color = "green",
    detect = { cmds = { "codex" }, title_pats = { "codex", "Codex" }, path_hints = { "codex" } },
    spawn = { cmd = "codex", default_args = {}, continue_flag = "", project_flag = nil },
    session = { dir = "~/.codex", file_pattern = "*.json" },
    status = {
      strategy = "tui_capture",
      working_pats = { "Thinking", "Running", "Executing" },
      waiting_pats = { "^>", "❯" },
    },
    project_mgmt = { tracks_branch = true, worktree_iso = true, session_file = true },
  },

  omnigent = {
    type  = "omnigent",
    label = "Omnigent",
    icon  = "O",
    color = "red",
    detect = {
      cmds       = { "omni", "omnigent" },
      title_pats = { "omni", "omnigent", "Omnigent" },
      path_hints = { "omni", "omnigent" },
    },
    spawn = {
      cmd           = "omni",
      default_args  = { "run", "--harness", "claude-sdk", "--server", "" },
      continue_flag = "--continue",
      project_flag  = nil,
    },
    session = {
      dir          = "~/.omnigent",
      file_pattern = "chat.db",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "Starting", "Preparing", "Connecting", "Launching", "Working", "Running" },
      waiting_pats = { "^>", "❯" },
    },
    project_mgmt = { tracks_branch = false, worktree_iso = false, session_file = true },
  },
}

M.order = { "pi", "cursor", "claude", "codex", "omnigent" }

function M.get(agent_type) return M.agents[agent_type] end

function M.all()
  local result = {}
  for _, key in ipairs(M.order) do
    if M.agents[key] then result[#result + 1] = M.agents[key] end
  end
  return result
end

function M.available()
  local result = {}
  for _, key in ipairs(M.order) do
    local agent = M.agents[key]
    if agent then
      for _, hint in ipairs(agent.detect.path_hints) do
        if vim.fn.exepath(hint) ~= "" then
          result[#result + 1] = agent
          break
        end
      end
    end
  end
  return result
end

function M.match_pane(cmd, title)
  for _, key in ipairs(M.order) do
    local agent = M.agents[key]
    local cmd_match = false
    for _, c in ipairs(agent.detect.cmds) do
      if cmd == c then cmd_match = true; break end
    end
    if cmd_match then
      if #agent.detect.title_pats > 0 then
        for _, pat in ipairs(agent.detect.title_pats) do
          if title:match(pat) then return agent end
        end
      else
        return agent
      end
    end
  end
  for _, key in ipairs(M.order) do
    local agent = M.agents[key]
    for _, pat in ipairs(agent.detect.title_pats) do
      if title:match(pat) then return agent end
    end
  end
  return nil
end

function M.expand_path(path)
  if not path then return nil end
  return vim.fn.expand(path)
end

function M.spawn_cmd(agent_type, dir, extra_args)
  local agent = M.agents[agent_type]
  if not agent then return nil end
  local bin = vim.fn.exepath(agent.spawn.cmd)
  if bin == "" then bin = agent.spawn.cmd end
  local parts = { bin }
  for _, arg in ipairs(agent.spawn.default_args) do parts[#parts + 1] = arg end
  if extra_args then
    for _, arg in ipairs(extra_args) do parts[#parts + 1] = arg end
  end
  local cmd = table.concat(parts, " ")
  if dir then cmd = "cd " .. vim.fn.shellescape(dir) .. " && " .. cmd end
  return cmd
end

M.status_icons = { waiting = "⏳", working = "⚙️ ", init = "✳ ", idle = "💤", unknown = "❓" }

function M.to_json()
  return vim.fn.json_encode({ version = M.VERSION, agents = M.agents, order = M.order })
end

function M.export(path)
  path = path or vim.fn.expand("~/.config/fleet/agent-registry.json")
  local dir = vim.fn.fnamemodify(path, ":h")
  vim.fn.mkdir(dir, "p")
  local f = io.open(path, "w")
  if f then f:write(M.to_json()); f:close(); return true end
  return false
end

return M
