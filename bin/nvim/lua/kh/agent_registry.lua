--- agent_registry.lua: Shared agent type definitions for fleet management.
---
--- Single source of truth for all supported AI coding agents. Consumed by
--- fleet.lua, harpoon-fleet.lua, cdev, and tmux layout scripts.
---
--- Registry version is bumped on any breaking schema change. Consumers
--- should check M.VERSION before operating on agent data.
---
--- Adding a new agent type:
---   1. Add entry to M.agents below
---   2. If custom status detection needed, add detector in M._detectors
---   3. Bump M.VERSION (minor for additions, major for schema changes)

local M = {}

-- ── Version ───────────────────────────────────────────
-- Semver: MAJOR.MINOR.PATCH
--   MAJOR: schema break (consumers must update)
--   MINOR: new agent type added (backwards compatible)
--   PATCH: detection tuning, bug fixes
M.VERSION = "1.0.0"

-- ── Agent Type Definitions ────────────────────────────
--
-- Schema per agent:
--   type          string   Unique key (used in CLI, logs, config)
--   label         string   Human-readable name
--   icon          string   Single icon for fleet display
--   color         string   ANSI color name for CLI output
--   detect = {
--     cmds          string[]  Process command names (pane_current_command)
--     title_pats    string[]  Lua patterns matched against pane_title
--     path_hints    string[]  Binary names to check via exepath
--   }
--   spawn = {
--     cmd           string   Binary to invoke
--     default_args  string[] Default arguments
--     continue_flag string   Flag to resume last conversation
--     project_flag  string   Flag to set working directory (if not cd-based)
--   }
--   session = {
--     dir           string   Session/log directory (~ expanded at runtime)
--     file_pattern  string   Glob for session files within dir
--   }
--   status = {
--     strategy      string   "tui_capture" | "process_state" | "output_scan"
--     working_pats  string[] Patterns in pane output indicating active work
--     waiting_pats  string[] Patterns indicating waiting for input
--   }
--   project_mgmt = {
--     tracks_branch boolean  Agent operates on git branches
--     worktree_iso  boolean  Agent uses git worktree isolation
--     session_file  boolean  Agent persists conversation to files
--   }

M.agents = {
  pi = {
    type  = "pi",
    label = "Pi Coding Agent",
    icon  = "π",
    color = "magenta",
    detect = {
      cmds       = { "node" },
      title_pats = { "^π", "^✳", "^pi:" },
      path_hints = { "pi" },
    },
    spawn = {
      cmd           = "pi",
      default_args  = {},
      continue_flag = "-c",
      project_flag  = nil, -- uses cd
    },
    session = {
      dir          = "~/.pi/agent/sessions",
      file_pattern = "*.jsonl",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "Working", "Running", "Executing" },
      waiting_pats = { "%$%d+%.%d+", "↑%d", "↓%d" },
    },
    project_mgmt = {
      tracks_branch = true,
      worktree_iso  = false,
      session_file  = true,
    },
  },

  claude = {
    type  = "claude",
    label = "Claude Code",
    icon  = "C",
    color = "cyan",
    detect = {
      cmds       = { "claude" },
      title_pats = { "claude", "Claude" },
      path_hints = { "claude" },
    },
    spawn = {
      cmd           = "claude",
      default_args  = {},
      continue_flag = "--continue",
      project_flag  = nil, -- uses cd
    },
    session = {
      dir          = "~/.claude/projects",
      file_pattern = "*.json",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
                       "Thinking", "Reading", "Editing", "Running",
                       "Searching", "Writing", "Creating" },
      waiting_pats = { "^>" , "^❯", "What would you like" },
    },
    project_mgmt = {
      tracks_branch = true,
      worktree_iso  = true,
      session_file  = true,
    },
  },

  codex = {
    type  = "codex",
    label = "Codex CLI",
    icon  = "X",
    color = "green",
    detect = {
      cmds       = { "codex" },
      title_pats = { "codex", "Codex" },
      path_hints = { "codex" },
    },
    spawn = {
      cmd           = "codex",
      default_args  = {},
      continue_flag = "",
      project_flag  = nil,
    },
    session = {
      dir          = "~/.codex",
      file_pattern = "*.json",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
                       "Thinking", "Running", "Executing" },
      waiting_pats = { "^>", "❯" },
    },
    project_mgmt = {
      tracks_branch = true,
      worktree_iso  = true,
      session_file  = true,
    },
  },

  gemini = {
    type  = "gemini",
    label = "Gemini CLI",
    icon  = "G",
    color = "blue",
    detect = {
      cmds       = { "gemini" },
      title_pats = { "gemini", "Gemini" },
      path_hints = { "gemini" },
    },
    spawn = {
      cmd           = "gemini",
      default_args  = {},
      continue_flag = "",
      project_flag  = nil,
    },
    session = {
      dir          = "~/.gemini",
      file_pattern = "*.json",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
                       "Thinking", "Running", "Searching" },
      waiting_pats = { "^>", "❯" },
    },
    project_mgmt = {
      tracks_branch = true,
      worktree_iso  = false,
      session_file  = true,
    },
  },

  ollama = {
    type  = "ollama",
    label = "Ollama",
    icon  = "O",
    color = "yellow",
    detect = {
      cmds       = { "ollama" },
      title_pats = { "ollama", "Ollama" },
      path_hints = { "ollama" },
    },
    spawn = {
      cmd           = "ollama",
      default_args  = { "run" },
      continue_flag = "",
      project_flag  = nil,
    },
    session = {
      dir          = "~/.ollama",
      file_pattern = "",
    },
    status = {
      strategy     = "output_scan",
      working_pats = { "^%S" },  -- streaming output = working
      waiting_pats = { "^>>>", "^> " },
    },
    project_mgmt = {
      tracks_branch = false,
      worktree_iso  = false,
      session_file  = false,
    },
  },

  opencode = {
    type  = "opencode",
    label = "OpenCode",
    icon  = "E",
    color = "red",
    detect = {
      cmds       = { "opencode" },
      title_pats = { "opencode", "OpenCode" },
      path_hints = { "opencode" },
    },
    spawn = {
      cmd           = "opencode",
      default_args  = {},
      continue_flag = "",
      project_flag  = nil,
    },
    session = {
      dir          = "~/.opencode",
      file_pattern = "*.json",
    },
    status = {
      strategy     = "tui_capture",
      working_pats = { "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
                       "Thinking", "Running", "Executing" },
      waiting_pats = { "^>", "❯" },
    },
    project_mgmt = {
      tracks_branch = true,
      worktree_iso  = false,
      session_file  = true,
    },
  },
}

-- ── Ordered list (for consistent display) ─────────────
-- Priority order: pi first (primary), then alphabetical
M.order = { "pi", "claude", "codex", "gemini", "ollama", "opencode" }

-- ── Lookup helpers ────────────────────────────────────

--- Get agent definition by type key.
function M.get(agent_type)
  return M.agents[agent_type]
end

--- Get all agent types as ordered list of definitions.
function M.all()
  local result = {}
  for _, key in ipairs(M.order) do
    if M.agents[key] then
      result[#result + 1] = M.agents[key]
    end
  end
  return result
end

--- Get types that have a binary available on this machine.
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

--- Match a tmux pane (cmd, title) against all registered agents.
--- Returns the agent definition or nil.
function M.match_pane(cmd, title)
  for _, key in ipairs(M.order) do
    local agent = M.agents[key]
    -- Check command name
    local cmd_match = false
    for _, c in ipairs(agent.detect.cmds) do
      if cmd == c then
        cmd_match = true
        break
      end
    end
    if cmd_match then
      -- If agent has title patterns, require at least one match
      if #agent.detect.title_pats > 0 then
        for _, pat in ipairs(agent.detect.title_pats) do
          if title:match(pat) then
            return agent
          end
        end
      else
        return agent
      end
    end
  end
  -- Fallback: check title patterns even without cmd match
  -- (some agents run under generic process names)
  for _, key in ipairs(M.order) do
    local agent = M.agents[key]
    for _, pat in ipairs(agent.detect.title_pats) do
      if title:match(pat) then
        return agent
      end
    end
  end
  return nil
end

--- Expand ~ in a path string.
function M.expand_path(path)
  if not path then return nil end
  return vim.fn.expand(path)
end

--- Get the spawn command for an agent type, optionally for a specific directory.
--- Returns the full shell command string.
function M.spawn_cmd(agent_type, dir, extra_args)
  local agent = M.agents[agent_type]
  if not agent then return nil end

  local bin = vim.fn.exepath(agent.spawn.cmd)
  if bin == "" then bin = agent.spawn.cmd end

  local parts = { bin }
  for _, arg in ipairs(agent.spawn.default_args) do
    parts[#parts + 1] = arg
  end
  if extra_args then
    for _, arg in ipairs(extra_args) do
      parts[#parts + 1] = arg
    end
  end

  local cmd = table.concat(parts, " ")
  if dir then
    cmd = "cd " .. vim.fn.shellescape(dir) .. " && " .. cmd
  end
  return cmd
end

-- ── Status icons (shared across fleet UI) ─────────────

M.status_icons = {
  waiting = "⏳",
  working = "⚙️ ",
  init    = "✳ ",
  idle    = "💤",
  unknown = "❓",
}

-- ── Export for CLI consumption ─────────────────────────
--- Serialize the registry to JSON (for cdev and other non-lua consumers).
function M.to_json()
  return vim.fn.json_encode({
    version = M.VERSION,
    agents  = M.agents,
    order   = M.order,
  })
end

--- Write registry JSON to a file (call from nvim to sync with CLI tools).
function M.export(path)
  path = path or vim.fn.expand("~/.config/fleet/agent-registry.json")
  local dir = vim.fn.fnamemodify(path, ":h")
  vim.fn.mkdir(dir, "p")
  local json = M.to_json()
  local f = io.open(path, "w")
  if f then
    f:write(json)
    f:close()
    return true
  end
  return false
end

return M
