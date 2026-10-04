# Dia Skill recipes

Paste into Dia → Skill Builder. Plain English. No secrets.

These are the continuation of the recovered Perplexity thread: Dia Skills that
make it easy to hand a page or prompt to pi.

## Skill: Steer pi from this tab

```text
Name: Steer pi

When I run this skill, copy the current tab title, URL, and any selected text.
Open or focus the local pi session that is already attached on this Mac.
Paste a single steering block:

New direction: <what I said after the skill name>
Why: recovered from Dia tab <title> <url>
Preserve: existing session work
Boundary: personal Mac; no work credentials
Report back with: what you changed or what is still blocked

If no pi session is attached, do not invent one. Tell me to run attach mac
or open the existing tmux/pi pane.
```

## Skill: Recover Perplexity thread for pi

```text
Name: Perplexity → pi

Open https://www.perplexity.ai/library if it is not already open.
Find the thread I name (or the currently open Perplexity tab).
Copy the user prompt verbatim and the first-pass answer outline.
Hand that exact prompt to the attached pi session as:

Resume this Perplexity prompt. Do not restate it. Execute it.
Thread: <title> <url>
Prompt:
<verbatim>

If you cannot see the thread body, say so and give me the URL only.
```

## Skill: Browser control handoff

```text
Name: Pi browser control

If Dia cannot drive the page itself, tell pi:

Use skill dia-browser. Preflight first.
Do not install browser-use or pi-browser-harness unless I say so.
Open this URL in Google Chrome and recover the visible prompt:
<url>
```

## After pasting

1. Trigger each skill once on a harmless tab (this skill page or Perplexity library).
2. Confirm the pi pane received the steer.
3. Do not grant Dia or pi extra permissions from the skill text. A skill cannot
   override sandbox policy.
