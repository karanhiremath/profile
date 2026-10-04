# pi-perplexity

Bridge so any pi (or Cursor) agent can look up, open, **drive the live
signed-in tab**, and route new asks through the official Perplexity API
when a key and quota exist.

Aliases: `pi-p`, `pi-perplexity`.

## Surfaces

| Need | Path |
|------|------|
| Library / existing thread / workspace pane | signed-in Chrome Default via AppleScript (no CDP) |
| Read pane, steer follow-up, download markdown | same tab, after Apple Events JS is enabled |
| New grounded ask | `POST /v1/agent` (or Sonar until 2026-09-27) if `PERPLEXITY_API_KEY` is under limit; else a new Chrome tab |
| Raw web hits | official `POST /search` |
| In-editor tools | official remote MCP `https://api.perplexity.ai/mcp` (OAuth). Not in this Cursor-bridge tool list until you Connect it. |

Web Pro/Max (the Chrome login) is **not** an API key. API usage tiers are a
separate API organization: https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers

Never: cookie theft, undocumented Perplexity REST, CDP on Chrome Default.

## One-time Chrome checkbox

Read / steer / md inject JavaScript through Apple Events:

**Google Chrome → View → Developer → Allow JavaScript from Apple Events**

Then `pi-p chrome-prep` and `pi-p read`. Tab list / open / new search URLs
work without that checkbox. With JS off, `read` still returns title/URL.

## Commands

```bash
pi-p tabs
pi-p focus c2ecf226-bb4b-4263-a1c1-690557005713
pi-p read
pi-p md
pi-p steer "summarize the open thread in 5 bullets"
pi-p steer "..." --dry                          # fill composer; no submit
pi-p new
pi-p new "latest Agent API presets"
pi-p search "latest Agent API presets"          # auto: API or browser
pi-p search "..." --dry                         # route only
pi-p search "..." --via browser
pi-p search "..." --via api --preset low
pi-p usage
pi-p route                                      # API vs Chrome split
pi-p route search
pi-p chrome-prep
pi-p workspace                              # focus Projects or open /projects
pi-p open workspace                         # Spaces redirects to Projects
pi-p mcp-status
pi-p mcp-install
pi-p lookup
pi-p open library
```

`sync` still writes metadata-first notes under
`~/src/notes/03_tech/agentic-os/fleet/perplexity/`. Full thread markdown
stays in `~/.local/share/pi-perplexity/downloads/`.
