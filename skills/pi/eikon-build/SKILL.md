---
name: eikon-build
description: Create, clone, customize, rasterize, and validate terminal eikon avatars and six-state animations for Herm. Use when building a new eikon, editing Ares, changing poses or animation loops, tuning glyphs/colors/crops, or preparing an editable local avatar package. Not for ordinary theme changes or publishing without approval.
---

# Build and customize eikons

Use the installed eikon toolchain and Herm Studio, not a new rasterizer or hand-edited frame dump. Work in a new local draft; never overwrite the active Ares package.

## Brief and toolchain

Confirm name, base character/source, intended change, terminal dimensions, color mode, and which states need distinct animations. For an Ares variant, keep Ares active until the draft passes review. Ask before generating new art through paid/network models.

Locate `eikon` on PATH or the installed package referenced by Herm's `node_modules/eikon`. Set `EIKON_CLI` to that package's `src/cli.tsx` when no executable exists. Read its README and `docs/SPEC.md`; read `docs/MANIFEST.md` before packaging. Installed versions are ground truth; do not fetch an unpinned CLI or guess its flags.

Prerequisites: Bun, chafa; ffmpeg for GIF/video. If missing, report the blocker and use the repo installer/package-manager convention after approval. Do not silently install or rewrite package locks.

## Media and layout

Use 48×24 cells and 16 fps as the starting point, then evaluate at the target terminal size. Keep silhouettes legible and avoid flicker. Keep source media beside the packed artifact so Studio edits are repeatable.

| State | Visual intent |
|---|---|
| idle | calm, low-motion baseline |
| listening | attentive/user-input pose |
| thinking | restrained progress animation |
| speaking | visible response animation |
| working | distinct tool-work motion |
| error | brief, readable error cue |

The packer accepts one image, one loop, or a directory:

```text
media/
  idle.png
  listening.png
  thinking/loop.mp4
  speaking/loop.mp4
  working/loop.mp4
  error/start.mp4
```

Missing states fall back to idle. A `<state>/start.mp4` is an intro/hold; adding `loop.mp4` gives intro then loop. Ares packages often put these under `states/`: pass that directory, not its package root. Explicitly include idle; do not rely on filesystem ordering as the fallback source.

## Pack, validate, preview

```sh
bun "${EIKON_CLI:?}" pack "${MEDIA_ROOT:?}" "${DRAFT_ROOT:?}/${EIKON_NAME:?}.eikon" \
  --name "${EIKON_NAME:?}" --width 48 --height 24 --fps 16 --symbols block --colors none
bun "${EIKON_CLI:?}" lint "${DRAFT_ROOT:?}/${EIKON_NAME:?}.eikon"
bun "${EIKON_CLI:?}" show "${DRAFT_ROOT:?}/${EIKON_NAME:?}.eikon"
```

Use `--colors 256|full` for colored art; check inversion rather than blindly keeping `--no-invert`. `show` is a poster/state-list sanity check, not animated visual verification. Preview all six states in an isolated Herm Studio/PTY and capture frames with `tty-eval`; never drive a live Cos pane with send-keys.

For interactive edits: Herm → Eikon → Studio. Create a draft, adopt source media, tune crop/pan/zoom, rasterizer, symbols, tone, and frame rate; save before selecting “use.” Packed-only avatars may lack editable source: recover source explicitly rather than pretending the packed frames are an editable image.

## Local package and delivery

Prepare a launch `eikon.package` manifest using the installed contract/library or supported package tooling. Include a relative runtime entrypoint, compatibility range, source mappings, and byte-exact size/digest descriptors when required. The registry `manifest`/`index` commands can rewrite an entire installed registry; do not run them there just to package one draft. No absolute paths or secret-like extras in the package.

Lint both `<name>.eikon` and `manifest.json`; inspect the local package with `herm eikon inspect <draft-dir> --json`. Install only into a named preview home initially. Activation is separate and requires the user to accept the preview. Default changes use `herm-eikon-defaults`.

Deliver draft path, source media, dimensions/fps, state coverage, lint/preview evidence, and unresolved visual choices. Public publish/submit/delist creates external writes: stop for approval of target and exact PR text. Never publish as a side effect of building.
