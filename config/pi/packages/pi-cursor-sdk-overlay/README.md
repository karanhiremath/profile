# pi-cursor-sdk-overlay

Replayable routing patch for installed `npm:pi-cursor-sdk`.

There is no writable 0.3.6 source checkout. After `pnpm update` of
`~/.pi/agent/npm`, re-run:

```
node ~/.pi/agent/local-packages/pi-cursor-sdk-overlay/apply.mjs
```

Patches:

- `CURSOR_PI_BRIDGE_PREFERENCE_TEXT` — `pi__subagent` is not optional when exposed
- bootstrap tool manifest — ban Cursor-native Task while `pi__subagent` is exposed
- `CallTool` args — inject `wait=false` on `pi__subagent` (chain stays `wait=true`)
