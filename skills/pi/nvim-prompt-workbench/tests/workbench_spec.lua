local M = dofile("scripts/workbench.lua")
local api = vim.api
-- Script mode disables events; enable them to exercise real save autocmd behavior.
vim.o.eventignore = ""
local root = vim.fn.tempname()
vim.fn.mkdir(root, "p", 448)
local job
local jobs = {}
local function check(ok, message) assert(ok, message) end
local function rejects(fn, pattern)
  local ok, err = pcall(fn)
  check(not ok and tostring(err):find(pattern, 1, true), "expected rejection: " .. pattern .. "; ok=" .. tostring(ok) .. "; result=" .. vim.inspect(err))
end
local function load(path, lines)
  vim.fn.writefile(lines, path)
  local buf = vim.fn.bufadd(path)
  vim.fn.bufload(buf)
  return buf
end
local ok, err = xpcall(function()
  local original_path, candidate_path = root .. "/original.md", root .. "/candidate.md"
  local original = load(original_path, { "Original intent" })
  local candidate = load(candidate_path, { "Candidate draft" })
  local before = M.snapshot(original)
  local expected = M.snapshot(candidate)
  local lines = { "Accepted edit", ":let g:workbench_executed = 1", "$(touch ignored)", "| quit!" }
  local saved = M.apply({ expected = expected, original_buf = original, lines = lines })
  check(not saved.modified and vim.deep_equal(vim.fn.readfile(candidate_path), lines), "accepted batch was not saved")
  check(vim.deep_equal(M.snapshot(original), before), "original changed")
  check(vim.g.workbench_executed == nil, "prompt text executed")
  rejects(function() M.apply({ expected = expected, original_buf = original, lines = { "stale" } }) end, "stale candidate")
  check(vim.deep_equal(vim.fn.readfile(candidate_path), lines), "stale apply changed disk")
  expected = M.snapshot(candidate)
  api.nvim_buf_set_lines(candidate, 0, -1, false, { "User typing" })
  rejects(function() M.apply({ expected = expected, original_buf = original, lines = { "overwrite" } }) end, "stale candidate")
  check(api.nvim_buf_get_lines(candidate, 0, -1, false)[1] == "User typing", "user edit lost")
  expected = M.snapshot(candidate)
  vim.fn.writefile({ "External writer" }, candidate_path)
  rejects(function() M.apply({ expected = expected, original_buf = original, lines = { "overwrite" } }) end, "disk changed")
  check(vim.fn.readfile(candidate_path)[1] == "External writer", "external write lost")
  -- Reconcile this disposable fixture before subsequent save tests; never force-write it.
  api.nvim_buf_call(candidate, function() vim.cmd("edit!") end)
  api.nvim_buf_set_lines(candidate, 0, -1, false, { "User typing" })
  rejects(function() M.apply({ expected = before, original_buf = original, lines = { "wrong" } }) end, "original buffer")
  local wrong_pid = vim.deepcopy(before)
  wrong_pid.pid = -1
  rejects(function() M.apply({ expected = wrong_pid, original_buf = original, lines = {} }) end, "PID differs")
  local alias_path = root .. "/alias.md"
  assert(vim.uv.fs_link(original_path, alias_path))
  local alias = vim.fn.bufadd(alias_path)
  vim.fn.bufload(alias)
  rejects(function() M.apply({ expected = M.snapshot(alias), original_buf = original, lines = { "alias" } }) end, "original")
  vim.o.columns, vim.o.lines = 120, 40
  local layout = M.layout({ expected_pid = vim.fn.getpid(), original_buf = original,
    candidate_path = candidate_path, optimizer_argv = { "cat" }, cwd = root, terminal_height = 8 })
  job = layout.terminal_job
  table.insert(jobs, job)
  for _, win in ipairs({ layout.original_win, layout.candidate_win }) do
    check(vim.wo[win].wrap and vim.wo[win].linebreak and vim.wo[win].breakindent, "unreadable wrapping")
    check(not vim.wo[win].diff and not vim.wo[win].foldenable, "deep diff/folds enabled")
  end
  check(#api.nvim_tabpage_list_wins(layout.tab) == 3, "expected three visible panes")
  check(api.nvim_win_get_position(layout.original_win)[1] == api.nvim_win_get_position(layout.candidate_win)[1], "prompts are not side by side")
  check(api.nvim_win_get_position(layout.terminal_win)[1] > api.nvim_win_get_position(layout.original_win)[1], "terminal is not below prompts")
  check(vim.bo[layout.terminal_buf].buftype == "terminal" and vim.fn.jobwait({ job }, 0)[1] == -1, "interactive terminal not running")
  check(api.nvim_buf_get_lines(candidate, 0, -1, false)[1] == "User typing", "layout replaced unsaved candidate")
  check(vim.deep_equal(M.snapshot(original), before), "layout changed original")
  local long_lines = {}
  for i = 1, 40 do long_lines[i] = "Readable line " .. i end
  M.apply({ expected = M.snapshot(candidate), original_buf = original, lines = long_lines })
  api.nvim_win_call(layout.candidate_win, function()
    vim.fn.winrestview({ lnum = 18, col = 3, topline = 12 })
  end)
  local reading_view = api.nvim_win_call(layout.candidate_win, function() return vim.fn.winsaveview() end)
  long_lines[1] = "Accepted first-line change"
  M.apply({ expected = M.snapshot(candidate), original_buf = original, lines = long_lines })
  local after_view = api.nvim_win_call(layout.candidate_win, function() return vim.fn.winsaveview() end)
  check(after_view.lnum == reading_view.lnum and after_view.col == reading_view.col
    and after_view.topline == reading_view.topline, "accepted save moved the reading view")
  api.nvim_create_autocmd("BufWritePost", { buffer = candidate, once = true, callback = function()
    api.nvim_buf_set_lines(candidate, 0, 1, false, { "Unsaved plugin change" })
    vim.bo[candidate].modified = true
  end })
  rejects(function() M.apply({ expected = M.snapshot(candidate), original_buf = original,
    lines = long_lines }) end, "remains modified")
  check(vim.bo[candidate].modified and vim.fn.readfile(candidate_path)[1] == long_lines[1],
    "post-save dirty state was hidden or reverted")
  for index, format in ipairs({
    { fileformat = "dos", fileencoding = "utf-8", bomb = true },
    { fileformat = "unix", fileencoding = "latin1", bomb = false },
    { fileformat = "mac", fileencoding = "utf-8", bomb = false },
    { fileformat = "unix", fileencoding = "utf-16le", bomb = true },
  }) do
    local formatted = load(root .. "/format-" .. index .. ".md", { "before" })
    for name, value in pairs(format) do vim.bo[formatted][name] = value end
    local format_ok, formatted_saved = pcall(M.apply, { expected = M.snapshot(formatted), original_buf = original,
      lines = { "caf\195\169", "second" } })
    check(format_ok, "format " .. index .. ": " .. tostring(formatted_saved))
    check(not formatted_saved.modified, "valid encoded save was rejected")
    M.apply({ expected = M.snapshot(formatted), original_buf = original, lines = { "" } })
  end
  local formatted = load(root .. "/formatter.md", { "before" })
  api.nvim_create_autocmd("BufWritePre", { buffer = formatted, once = true, callback = function()
    api.nvim_buf_set_lines(formatted, 0, 1, false, { "Formatter result" })
  end })
  check(M.apply({ expected = M.snapshot(formatted), original_buf = original, lines = { "accepted" } }).lines[1]
    == "Formatter result", "saved formatter output was rejected")
  local request_path, output_path = root .. "/request.json", root .. "/snapshot.json"
  vim.fn.writefile({ vim.json.encode({ op = "snapshot", buffer = original, output_path = output_path }) }, request_path)
  M.request(request_path)
  check(vim.json.decode(table.concat(vim.fn.readfile(output_path), "\n")).sha256 == before.sha256, "snapshot receipt wrong")
  check(bit.band(vim.uv.fs_stat(output_path).mode, 511) == 384, "snapshot permissions are not private")
  rejects(function() M.request(request_path) end, "EEXIST")
  local candidate_before_receipt = M.snapshot(candidate)
  local tab_count = #api.nvim_list_tabpages()
  vim.fn.writefile({ vim.json.encode({ op = "apply", expected = candidate_before_receipt,
    original_buf = original, lines = { "Must not apply" }, output_path = output_path }) }, request_path)
  rejects(function() M.request(request_path) end, "EEXIST")
  check(vim.deep_equal(M.snapshot(candidate), candidate_before_receipt), "receipt collision occurred after mutation")
  vim.fn.writefile({ vim.json.encode({ op = "layout", expected_pid = vim.fn.getpid(), original_buf = original,
    candidate_path = candidate_path, optimizer_argv = { "cat" }, output_path = output_path }) }, request_path)
  rejects(function() M.request(request_path) end, "EEXIST")
  check(#api.nvim_list_tabpages() == tab_count, "receipt collision created a layout/terminal")
  local error_receipt = root .. "/failed-request.json"
  vim.fn.writefile({ vim.json.encode({ op = "apply", expected = wrong_pid,
    original_buf = original, lines = {}, output_path = error_receipt }) }, request_path)
  rejects(function() M.request(request_path) end, "PID differs")
  check(vim.json.decode(table.concat(vim.fn.readfile(error_receipt), "\n")).status == "error", "failed request receipt missing")
  local check_env_path, env_verified = root .. "/check-env.lua", root .. "/env-verified"
  local stripped = { "PI_SESSION_ID", "CDEV_SESSION_ID", "PI_JOBS_DIR", "PI_JOB_ID",
    "CURSOR_TEST_BINDING", "PI_CURSOR_TEST_BINDING", "MCP_TEST_BINDING", "__CURSOR_TEST_BINDING" }
  local child_checks = {}
  for _, name in ipairs(stripped) do
    vim.env[name] = "synthetic-parent-binding"
    table.insert(child_checks, "assert(vim.env[" .. vim.inspect(name) .. "] == nil)")
  end
  vim.env.PI_CURSOR_LOCAL_RESUME, vim.env.PI_JOB_BUS_STEER_SELF = "1", "1"
  vim.env.NVIM_WORKBENCH_TEST_DEFAULT = "preserved-default"
  table.insert(child_checks, 'assert(vim.env.PI_CURSOR_LOCAL_RESUME == "0")')
  table.insert(child_checks, 'assert(vim.env.PI_JOB_BUS_STEER_SELF == "0")')
  table.insert(child_checks, 'assert(vim.env.NVIM_WORKBENCH_TEST_DEFAULT == "preserved-default")')
  table.insert(child_checks, 'vim.fn.writefile({"verified"}, ' .. vim.inspect(env_verified) .. ')')
  table.insert(child_checks, 'vim.cmd("sleep 30")')
  vim.fn.writefile(child_checks, check_env_path)
  local env_layout = M.layout({ expected_pid = vim.fn.getpid(), original_buf = original,
    candidate_path = candidate_path, optimizer_argv = { vim.v.progpath, "--headless", "--clean", "-i", "NONE", "-l", check_env_path }, cwd = root })
  table.insert(jobs, env_layout.terminal_job)
  check(vim.wait(3000, function() return vim.fn.filereadable(env_verified) == 1 end, 20), "optimizer inherited parent routing or lost defaults")
  print("PASS: accepted save; stale buffer/disk rejection; original/alias/PID guards; literal text; readable splits; interactive terminal; view preservation; post-save dirty reporting; encoded/formatter saves; private preflighted receipts; isolated optimizer routing")
end, debug.traceback)
for _, child in ipairs(jobs) do pcall(vim.fn.jobstop, child) end
vim.fn.delete(root, "rf")
if not ok then io.stderr:write(err .. "\n"); vim.cmd("cquit 1") end
vim.cmd("qa!")
