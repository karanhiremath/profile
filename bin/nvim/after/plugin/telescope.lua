-- Telescope config has moved into the plugin spec's config function in lua/kh/lazy.lua.
-- With lazy.nvim, after/plugin/ files run before plugins are loaded, so setup must
-- live in the spec's config = function() to guarantee telescope is available.

