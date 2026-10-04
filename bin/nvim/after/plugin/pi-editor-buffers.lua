-- Additive: capture pi external-editor buffers at :w time.
-- Live dirs are deleted when the editor exits, so write-time copy is required.
local group = vim.api.nvim_create_augroup("PiEditorBuffers", { clear = true })

vim.api.nvim_create_autocmd("BufWritePost", {
  group = group,
  pattern = "*/pi-editor-*/prompt.md",
  callback = function(args)
    pcall(function()
      local src = vim.fn.resolve(vim.fn.fnamemodify(args.file, ":p"))
      if type(src) ~= "string" or src == "" then
        return
      end
      if not src:match("pi%-editor%-[^/]+/prompt%.md$") then
        return
      end

      local worktree = vim.fn.expand("~/src/notes-pi-buffers")
      if vim.fn.isdirectory(worktree) == 0 then
        return
      end

      local dest_dir = worktree .. "/pi-buffers"
      vim.fn.mkdir(dest_dir, "p")

      local parent = vim.fn.fnamemodify(src, ":h:t")
      local ts = os.date("!%Y%m%dT%H%M%SZ")
      local dest = string.format("%s/%s-%s.md", dest_dir, ts, parent)
      local lines = vim.fn.readfile(src, "b")
      vim.fn.writefile(lines, dest, "b")

      local buffers = vim.fn.expand("~/.pi/agent/buffers")
      vim.fn.mkdir(buffers, "p", 448) -- 0700
      local index = buffers .. "/INDEX.jsonl"
      local size = vim.fn.getfsize(src)
      if type(size) ~= "number" or size < 0 then
        size = 0
      end

      local pane_id = os.getenv("TMUX_PANE")
      if type(pane_id) ~= "string" or pane_id == "" then
        pane_id = nil
      end

      local session_hint = nil
      if pane_id then
        local ok, tmux_hint = pcall(function()
          return vim.fn.system({ "tmux", "display-message", "-p", "-t", pane_id, "#S:#I.#P" })
        end)
        if ok and vim.v.shell_error == 0 and type(tmux_hint) == "string" then
          tmux_hint = tmux_hint:gsub("%s+$", "")
          if tmux_hint ~= "" then
            session_hint = tmux_hint
          end
        end
      end

      local rec = string.format(
        '{"ts":%s,"path":%s,"session_hint":%s,"size":%d,"buffer_dir":%s,"pane_id":%s}\n',
        vim.fn.json_encode(ts),
        vim.fn.json_encode(src),
        session_hint == nil and "null" or vim.fn.json_encode(session_hint),
        size,
        vim.fn.json_encode(parent),
        pane_id == nil and "null" or vim.fn.json_encode(pane_id)
      )
      local f = io.open(index, "a")
      if f then
        f:write(rec)
        f:close()
      end
    end)
  end,
})
