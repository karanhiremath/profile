-- atop vi RPC helper. Trusted editor code; request JSON is data.
-- Snapshot + write the selected prompt buffer. Never send keys.
local M = {}
local api, uv = vim.api, vim.uv

local function require_value(ok, message)
  if not ok then error("atop-vi: " .. message, 0) end
end

local function buffer_id(buf)
  require_value(type(buf) == "number" and buf % 1 == 0, "buffer must be an integer")
  if buf == 0 then buf = api.nvim_get_current_buf() end
  require_value(api.nvim_buf_is_valid(buf) and api.nvim_buf_is_loaded(buf), "buffer is not loaded")
  require_value(vim.bo[buf].buftype == "", "expected a normal prompt buffer")
  return buf
end

local function find_buffer(path)
  require_value(type(path) == "string" and path ~= "", "path is required")
  for _, buf in ipairs(api.nvim_list_bufs()) do
    if api.nvim_buf_is_loaded(buf) and vim.bo[buf].buftype == "" then
      if api.nvim_buf_get_name(buf) == path then
        return buf
      end
    end
  end
  error("atop-vi: no loaded buffer for " .. path, 0)
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
  return { exists = true, sha256_base64 = vim.fn.sha256(vim.base64.encode(bytes)), dev = stat.dev, ino = stat.ino }
end

function M.snapshot(buf)
  buf = buffer_id(buf)
  local lines = api.nvim_buf_get_lines(buf, 0, -1, false)
  local path = api.nvim_buf_get_name(buf)
  return {
    pid = vim.fn.getpid(),
    server = vim.v.servername,
    buffer = buf,
    path = path,
    changedtick = api.nvim_buf_get_changedtick(buf),
    modified = vim.bo[buf].modified,
    sha256 = vim.fn.sha256(vim.json.encode(lines)),
    disk = disk(path),
    lines = lines,
  }
end

function M.list()
  local out = {}
  for _, buf in ipairs(api.nvim_list_bufs()) do
    if api.nvim_buf_is_loaded(buf) and vim.bo[buf].buftype == "" then
      local path = api.nvim_buf_get_name(buf)
      if path ~= "" then
        out[#out + 1] = { buffer = buf, path = path, modified = vim.bo[buf].modified }
      end
    end
  end
  return { pid = vim.fn.getpid(), server = vim.v.servername, buffers = out }
end

local function read_lines_file(path)
  require_value(type(path) == "string" and path:sub(1, 1) == "/", "file must be absolute")
  local file, err = io.open(path, "rb")
  require_value(file ~= nil, err or "cannot read write file")
  local raw = file:read("*a")
  file:close()
  if raw == "" then return { "" } end
  raw = raw:gsub("\r\n", "\n"):gsub("\r", "\n")
  if raw:sub(-1) == "\n" then raw = raw:sub(1, -2) end
  return vim.split(raw, "\n", { plain = true })
end

function M.write(opts)
  require_value(type(opts) == "table", "write opts required")
  local buf
  if opts.buffer then
    buf = buffer_id(opts.buffer)
  else
    buf = find_buffer(opts.path)
  end
  if opts.expected_pid then
    require_value(opts.expected_pid == vim.fn.getpid(), "editor PID differs from the selected snapshot")
  end
  local lines = opts.lines
  if opts.file then
    lines = read_lines_file(opts.file)
  end
  require_value(type(lines) == "table", "lines or file required")
  api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  api.nvim_buf_call(buf, function()
    local confirm = vim.o.confirm
    vim.o.confirm = false
    local ok, err = pcall(function()
      vim.cmd({ cmd = "write", bang = true, mods = { silent = true, emsg_silent = true } })
    end)
    vim.o.confirm = confirm
    require_value(ok, tostring(err))
  end)
  return M.snapshot(buf)
end

function M.request(path)
  local file, err = io.open(path, "rb")
  require_value(file ~= nil, err or "cannot read request")
  local encoded = file:read("*a")
  file:close()
  local opts = vim.json.decode(encoded)
  require_value(opts.op == "snapshot" or opts.op == "list" or opts.op == "write", "unknown operation")
  local fd
  if opts.output_path then
    require_value(type(opts.output_path) == "string" and opts.output_path:sub(1, 1) == "/",
      "output_path must be absolute")
    local open_err
    fd, open_err = uv.fs_open(opts.output_path, "wx", 384)
    require_value(fd ~= nil, open_err or "cannot reserve private result file")
  end
  local ok, result = pcall(function()
    if opts.op == "snapshot" then
      if opts.path and not opts.buffer then
        return M.snapshot(find_buffer(opts.path))
      end
      return M.snapshot(opts.buffer or 0)
    elseif opts.op == "list" then
      return M.list()
    else
      return M.write(opts)
    end
  end)
  if fd then
    local receipt = ok and result or { status = "error", operation = opts.op, error = tostring(result) }
    local bytes = vim.json.encode(receipt) .. "\n"
    local written, write_err = uv.fs_write(fd, bytes, 0)
    uv.fs_close(fd)
    if written ~= #bytes then
      return vim.json.encode({
        status = ok and "completed_receipt_failed" or "operation_and_receipt_failed",
        operation = opts.op,
        output_path = opts.output_path,
        pid = vim.fn.getpid(),
        error = write_err or "incomplete result write",
        inspect_before_retry = true,
      })
    end
  end
  require_value(ok, tostring(result))
  if opts.output_path then
    return vim.json.encode({ output_path = opts.output_path, pid = vim.fn.getpid() })
  end
  return vim.json.encode(result)
end

return M
