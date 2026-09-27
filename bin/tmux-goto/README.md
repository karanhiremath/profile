# tmux-goto — clickable deep links to a tmux pane

Print `fips:3.1` (tmux's own `session:window.pane` target syntax) in a way
that, if clicked in Ghostty, jumps straight there.

## What Ghostty actually supports (checked August 2026)

- **OSC 8 hyperlinks: yes.** Ghostty renders `\e]8;;URI\e\\text\e]8;;\e\\` as
  a clickable link and opens `URI` via the system opener (`xdg-open` on
  Linux, `open` on macOS) on ctrl/cmd-click.
- **A config-level way to bind matched text/URIs to an arbitrary command
  inside Ghostty itself: no, not yet.** Ghostty's config schema has a `link`
  field for exactly this (regex match -> open / arbitrary binding action),
  but as of this writing it is scaffolding only — the field's own doc comment
  in `Config.zig` says `TODO: This can't currently be set!`. The feature is
  tracked upstream (ghostty-org/ghostty discussions #9545/#9546/#9547,
  "Almost-accepted feature request pending design"). When it ships, this
  whole custom-scheme dance becomes unnecessary — a `link` rule could just
  exec the switch directly.
- **Custom URI scheme handling: not inside Ghostty.** Ghostty has no config
  for "scheme X routes to command Y" — any URL it opens goes to the OS's
  default handler for that URL. So a custom `tmux-goto://` scheme has to be
  registered with the **OS**, not with Ghostty.

## The mechanism this ships

1. `tmux-pane-link <target>` prints an OSC 8 hyperlink whose href is
   `tmux-goto://<target>` and whose visible text is `<target>` itself (e.g.
   `fips:3.1`). It also always prints the manual command
   (`tmux switch-client -t <target>`) to stderr, so the output is useful even
   before/without registration, and even if you're on a terminal with no OSC
   8 support at all.
2. `bin/tmux-goto/install` registers `handler` as the OS's default opener for
   `x-scheme-handler/tmux-goto` (Linux: `xdg-mime` + a `.desktop` file in
   `~/.local/share/applications`; macOS: an `osacompile`-built AppleScript
   `.app` in `~/Applications` with `CFBundleURLTypes` added to its
   `Info.plist`, registered via `lsregister`).
3. `handler <tmux-goto://target>` strips the scheme, then:
   - If the session exists on the **local** tmux server: `switch-client` if
     this process happens to be inside an attached client (rare — see
     caveat below), otherwise opens a new terminal that attaches and
     `select-pane`s to the target.
   - If not found locally: walks `bin/tmux/hosts/registry.conf` (the same
     registry `tmux-connect` uses), SSHes into each remote host to check for
     a same-named session, and if found opens a terminal that SSHes in and
     attaches there.
   - If found nowhere: logs to `~/.cache/tmux-goto.log` and best-effort
     desktop-notifies (`notify-send` / `osascript`), exits 1.

## Where the registration has to actually happen

**Register on the machine running the terminal emulator that will receive
the click** — not on whatever host the tmux session itself lives on. If
Ghostty runs on your Mac and you SSH into a Linux box to view a tmux session
there, the click fires on the Mac; `just tmux-goto` needs to have been run on
the Mac, and `bin/tmux/hosts/registry.conf` needs an entry for that Linux
box so `handler`'s remote fallback can find it.

## Known caveats — read before trusting this fully

- **macOS path is unverified.** This was built and installed from a Linux
  sandbox with no real Mac available to click-test on. The `osacompile` +
  `CFBundleURLTypes` + `lsregister` approach is a documented, standard
  technique for wiring a custom URL scheme to a script without compiling a
  real app — but "should work" is not "verified working." After `just
  tmux-goto` on a Mac, test with `open 'tmux-goto://fips:3.1'` and confirm a
  line lands in `~/.cache/tmux-goto.log` before relying on it.
- **No ambient `$TMUX` when a link is clicked.** A click dispatches through
  the OS opener as a fresh process, not as a child of whatever tmux client's
  pane displayed the link — so `handler` cannot assume it's "inside" tmux
  and cannot just call `switch-client` from wherever it runs. It opens a new
  terminal window that attaches instead. This means clicking a link always
  gets you a (new-ish) window on the target session, not a silent switch of
  your current window — that's a deliberate, correct tradeoff, not a bug.
- **`select-pane`/`select-window` changes the session's active window for
  every client attached to it**, not just the new one — this is normal tmux
  behavior (window "current-ness" is per-session, not per-client), same as
  what already happens when you switch windows manually.
- **Ghostty's `-e` may prompt.** Ghostty has a one-time "Allow Ghostty to
  Execute" confirmation for some `-e` invocations; the first click may need
  that dialog dismissed.
- **Session-name assumption.** `handler` splits the target on the first `:`
  to get the session name; a session name containing `:` or `.` will break
  this (tmux itself discourages such names).

## Usage

```bash
just tmux-goto                    # one-time: link binaries, register scheme
tmux-pane-link fips:3.1           # print a clickable link + manual fallback
tmux-pane-link fips:3.1 --plain   # just the text, no OSC 8 wrapping
tmux-pane-link fips:3.1 --quiet   # suppress the manual-command stderr line
```
