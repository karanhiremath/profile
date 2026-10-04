---
name: pi-perplexity
description: "pi <> Perplexity bridge. Use when the user mentions Perplexity, pplx, pi-p, live tab, library, steer, download markdown, API limits, or Perplexity MCP."
user-invocable: true
argument-hint: "tabs|read|steer|search|usage|md"
---

# pi <> Perplexity bridge

A new agent does **not** automatically see Perplexity. Call this bridge.

```bash
pi-p context
pi-p tabs
pi-p focus <uuid|window:tab>
pi-p read
pi-p md
pi-p steer "<follow-up>"
pi-p steer "<follow-up>" --dry # fill composer only; do not submit
pi-p search "<query>"          # API if keyed+quota, else live tab
pi-p search "<query>" --dry    # route only; no quota, no new tab
pi-p usage
pi-p route                     # API vs Chrome split
pi-p chrome-prep
pi-p workspace                 # focus Projects tab or open /projects
pi-p open workspace            # same (Spaces redirects to Projects)
```

Aliases: `pi-p`, `pi-perplexity`.

## Route

| Action | Via |
|--------|-----|
| tabs / focus / read / steer / md / library / workspace | signed-in Chrome Default, AppleScript, **no CDP** |
| search / ask | official Agent API (`POST /v1/agent`) when `PERPLEXITY_API_KEY` is set and under local RPM/cooldown; else a new Chrome tab |
| MCP search/ask/research/reason | official remote MCP `https://api.perplexity.ai/mcp` **only if connected** in Cursor Settings |

This Cursor-bridge run has no Perplexity MCP tools until the user Connects
`pi-p mcp-install`. Do not pretend `pi__subagent` or Perplexity MCP tools
exist here.

Web Pro/Max login ≠ API credits. Do not steal cookies. Do not call
undocumented REST.

## Live pane

`pi-p read` / `steer` / `md` need one Chrome checkbox:

View → Developer → Allow JavaScript from Apple Events

`pi-p tabs` / `open` / `new` / URL search work without it.
`pi-p read` falls back to title/URL metadata when JS is off.
`pi-p chrome-prep` writes the Chrome defaults key and tries the menu item;
osascript cannot click it without Accessibility. The checkbox is the gate.
Official Agent Tier 0 is 50 RPM / 1 QPS; Search is 50 query units/s.
`pi-p usage` prints those facts. Web login ≠ API credits.

## Notes cron

`pi-p install-cron` every 6h: catalog only. Full markdown from `pi-p md`
stays in `~/.local/share/pi-perplexity/downloads/`, not the vault.

Skill directory: this file's parent.
