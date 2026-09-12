-- Native prompt-workbench operations. This module is trusted editor code, not a sandbox.
local M = {}
local api, uv = vim.api, vim.uv

local function require_value(ok, message)
  if not ok then error("prompt-workbench: " .. message, 0) end
end

local function buffer_id(buf)
  require_value(type(buf) == "number" and buf % 1 == 0, "buffer must be an integer")
  if buf == 0 then buf = api.nvim_get_current_buf() end
  require_value(api.nvim_buf_is_valid(buf) and api.nvim_buf_is_loaded(buf), "buffer is not loaded")
  require_value(vim.bo[buf].buftype == "", "expected a normal prompt buffer")
  return buf
end

local function disk(path)
  if path == "" then return { exists = false } end
  local stat = uv.fs_stat(path)
  if not stat then return { exists = false } end
  require_value(stat.type == "file", "prompt path is not a regular file")
  local file, err = io.open(path, "rb")
  require_value(file ~= nil, err or "cannot read prompt file")
  local bytes = file:read("*a")
  file:close()
  -- Vim's sha256() cannot accept NUL-containing strings (e.g. UTF-16 files).
  return { exists = true, sha256_base64 = vim.fn.sha256(vim.base64.encode(bytes)), dev = stat.dev, ino = stat.ino }
end

function M.snapshot(buf)
  buf = buffer_id(buf)
  local lines = api.nvim_buf_get_lines(buf, 0, -1, false)
  local path = api.nvim_buf_get_name(buf)
  return {
    pid = vim.fn.getpid(), server = vim.v.servername, buffer = buf, path = path,
    changedtick = api.nvim_buf_get_changedtick(buf), modified = vim.bo[buf].modified,
    sha256 = vim.fn.sha256(vim.json.encode(lines)), disk = disk(path), lines = lines,
  }
end

local function identity(pid)
  require_value(pid == vim.fn.getpid(), "editor PID differs from the selected snapshot")
end

local function separate(candidate, original)
  original = buffer_id(original)
  require_value(candidate ~= original, "candidate is the original buffer")
  local a, b = api.nvim_buf_get_name(candidate), api.nvim_buf_get_name(original)
  require_value(a ~= "" and a ~= b, "candidate needs a separate named file")
  local da, db = disk(a), disk(b)
  require_value(not (da.exists and db.exists and da.dev == db.dev and da.ino == db.ino),
    "candidate aliases the original file")
end

local function guard(expected)
  require_value(type(expected) == "table", "expected snapshot object is required")
  identity(expected.pid)
  local current = M.snapshot(expected.buffer)
  for _, key in ipairs({ "path", "changedtick", "modified", "sha256" }) do
    require_value(current[key] == expected[key], "stale candidate " .. key .. "; rebase the proposal")
  end
  require_value(vim.deep_equal(current.disk, expected.disk), "disk changed; reconcile before saving")
  return current.buffer
end

local function written_lines(buf)
  local compare = api.nvim_create_buf(false, true)
  vim.bo[compare].modeline = false
  vim.bo[compare].fileencoding = vim.bo[buf].fileencoding
  vim.bo[compare].fileformat = vim.bo[buf].fileformat
  vim.bo[compare].binary = vim.bo[buf].binary
  api.nvim_buf_set_lines(compare, 0, -1, false, { "workbench verification" })
  local ok, result = pcall(function()
    api.nvim_buf_call(compare, function()
      local formats, encodings = vim.o.fileformats, vim.o.fileencodings
      vim.o.fileformats, vim.o.fileencodings = "", ""
      local read_ok, read_err = pcall(api.nvim_cmd, {
        cmd = "read", range = { 1 }, args = { api.nvim_buf_get_name(buf) },
        mods = { noautocmd = true, silent = true, keepalt = true, keepjumps = true },
        magic = { file = false, bar = false } }, {})
      vim.o.fileformats, vim.o.fileencodings = formats, encodings
      require_value(read_ok, tostring(read_err))
    end)
    local lines = api.nvim_buf_get_lines(compare, 1, -1, false)
    return #lines == 0 and { "" } or lines
  end)
  api.nvim_buf_delete(compare, { force = true })
  require_value(ok, "cannot verify saved text; inspect before retrying: " .. tostring(result))
  return result
end

function M.apply(opts)
  local buf = guard(opts.expected)
  separate(buf, opts.original_buf)
  require_value(vim.bo[buf].modifiable and not vim.bo[buf].readonly, "candidate is not writable")
  require_value(type(opts.lines) == "table" and vim.islist(opts.lines), "lines must be an array")
  for _, line in ipairs(opts.lines) do
    require_value(type(line) == "string" and not line:find("\n", 1, true), "each line must be a string without a newline")
  end
  local views = {}
  for _, win in ipairs(api.nvim_list_wins()) do
    if api.nvim_win_get_buf(win) == buf then
      views[win] = api.nvim_win_call(win, function() return vim.fn.winsaveview() end)
    end
  end
  local ok, err = pcall(function()
    api.nvim_buf_set_lines(buf, 0, -1, false, opts.lines)
    api.nvim_buf_call(buf, function() vim.cmd("silent keepalt write") end)
  end)
  for win, view in pairs(views) do
    if api.nvim_win_is_valid(win) and api.nvim_win_get_buf(win) == buf then
      api.nvim_win_call(win, function() vim.fn.winrestview(view) end)
    end
  end
  require_value(ok, "save failed; inspect the visible candidate before retrying: " .. tostring(err))
  local saved = M.snapshot(buf)
  -- BufWritePost may change text while Neovim restores the old modified flag.
  -- Compare decoded disk text as well, allowing BufWritePre formatters to save normally.
  if not vim.deep_equal(saved.lines, written_lines(buf)) then
    vim.bo[buf].modified = true
    error("prompt-workbench: save completed but candidate differs from disk and remains modified; inspect before retrying", 0)
  end
  require_value(not saved.modified, "save completed but candidate remains modified; inspect before retrying")
  return saved
end

local function readable(win)
  for name, value in pairs({ wrap = true, linebreak = true, breakindent = true,
    diff = false, scrollbind = false, cursorbind = false, foldenable = false }) do
    api.nvim_set_option_value(name, value, { win = win })
  end
end

function M.layout(opts)
  identity(opts.expected_pid)
  local original = buffer_id(opts.original_buf)
  require_value(type(opts.candidate_path) == "string" and opts.candidate_path:sub(1, 1) == "/",
    "candidate_path must be absolute")
  local candidate_stat = uv.fs_stat(opts.candidate_path)
  require_value(candidate_stat and candidate_stat.type == "file", "candidate file must already exist")
  require_value(not (opts.terminal_buf and opts.optimizer_argv), "select terminal_buf or optimizer_argv")
  local argv = opts.optimizer_argv or { "pi" }
  if opts.terminal_buf then
    require_value(api.nvim_buf_is_valid(opts.terminal_buf) and vim.bo[opts.terminal_buf].buftype == "terminal",
      "terminal_buf must identify an existing terminal")
  else
    require_value(type(argv) == "table" and vim.islist(argv) and #argv > 0, "optimizer_argv must be an argv array")
    for _, item in ipairs(argv) do require_value(type(item) == "string", "argv entries must be strings") end
    require_value(vim.fn.executable(argv[1]) == 1, "optimizer executable was not found")
  end
  local cwd = opts.cwd or vim.fn.getcwd()
  local cwd_stat = uv.fs_stat(cwd)
  require_value(cwd_stat and cwd_stat.type == "directory", "cwd is not a directory")
  local candidate = vim.fn.bufadd(opts.candidate_path)
  vim.bo[candidate].modeline = false
  vim.fn.bufload(candidate)
  separate(candidate, original)
  vim.cmd("tabnew")
  local original_win = api.nvim_get_current_win()
  api.nvim_win_set_buf(original_win, original)
  vim.cmd("rightbelow vsplit")
  local candidate_win = api.nvim_get_current_win()
  api.nvim_win_set_buf(candidate_win, candidate)
  readable(original_win)
  readable(candidate_win)
  vim.cmd("wincmd =")
  vim.cmd("botright split")
  local terminal_win = api.nvim_get_current_win()
  local terminal = opts.terminal_buf or api.nvim_create_buf(false, true)
  api.nvim_win_set_buf(terminal_win, terminal)
  api.nvim_win_set_height(terminal_win, math.max(3, math.floor(opts.terminal_height or 10)))
  local job = vim.b[terminal].terminal_job_id
  if not opts.terminal_buf then
    local env = vim.fn.environ()
    for name in pairs(env) do
      if name == "PI_SESSION_ID" or name == "PI_JOBS_DIR" or name:match("^CDEV_SESSION")
        or name:match("^PI_JOB_") or name:match("^CURSOR_") or name:match("^PI_CURSOR_")
        or name:match("^MCP_") or name:match("^__CURSOR_") then env[name] = nil end
    end
    env.PI_CURSOR_LOCAL_RESUME = "0"
    env.PI_JOB_BUS_STEER_SELF = "0"
    job = vim.fn.jobstart(argv, { term = true, cwd = cwd, clear_env = true, env = env })
    require_value(job > 0, "terminal launch failed; inspect the workbench")
  end
  return { pid = vim.fn.getpid(), tab = api.nvim_get_current_tabpage(),
    original_win = original_win, candidate_win = candidate_win, terminal_win = terminal_win,
    terminal_buf = terminal, terminal_job = job, candidate = M.snapshot(candidate) }
end

function M.request(path)
  local file, err = io.open(path, "rb")
  require_value(file ~= nil, err or "cannot read request")
  local encoded = file:read("*a")
  file:close()
  local opts = vim.json.decode(encoded)
  require_value(opts.op == "snapshot" or opts.op == "apply" or opts.op == "layout", "unknown operation")
  local fd
  if opts.output_path then
    require_value(type(opts.output_path) == "string" and opts.output_path:sub(1, 1) == "/",
      "output_path must be absolute")
    local open_err
    fd, open_err = uv.fs_open(opts.output_path, "wx", 384)
    require_value(fd ~= nil, open_err or "cannot reserve private result file")
  end
  local ok, result = pcall(function()
    if opts.op == "snapshot" then return M.snapshot(opts.buffer)
    elseif opts.op == "apply" then return M.apply(opts)
    else return M.layout(opts) end
  end)
  if fd then
    local receipt = ok and result or { status = "error", operation = opts.op, error = tostring(result) }
    local bytes = vim.json.encode(receipt) .. "\n"
    local written, write_err = uv.fs_write(fd, bytes, 0)
    uv.fs_close(fd)
    if written ~= #bytes then
      return vim.json.encode({ status = ok and "completed_receipt_failed" or "operation_and_receipt_failed",
        operation = opts.op, output_path = opts.output_path, pid = vim.fn.getpid(),
        error = write_err or "incomplete result write", inspect_before_retry = true })
    end
  end
  require_value(ok, tostring(result))
  if opts.output_path then
    return vim.json.encode({ output_path = opts.output_path, pid = vim.fn.getpid() })
  end
  return vim.json.encode(result)
end

return M
