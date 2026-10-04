-- cmdk: same action bar as Ghostty Cmd-K / tmux prefix+C-k / zsh ^X^K
local M = {}

local function cmdk_bin()
  local profile = os.getenv("PROFILE_DIR") or (os.getenv("HOME") .. "/src/profile")
  return profile .. "/bin/cmdk/cmdk"
end

function M.popup()
  if os.getenv("TMUX") and os.getenv("TMUX") ~= "" then
    vim.fn.jobstart({ cmdk_bin(), "popup" }, { detach = true })
    return
  end
  vim.cmd("tabnew | terminal " .. vim.fn.fnameescape(cmdk_bin()) .. " pick")
end

function M.setup()
  vim.keymap.set("n", "<leader>k", M.popup, { desc = "cmdk action bar" })
end

return M
