#!/usr/bin/env python3
"""Unit tests for atop.live.v1 collector (no live tmux required)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import live


class Classify(unittest.TestCase):
    def test_harness(self) -> None:
        self.assertEqual(live.classify_cmd("pi", "π - profile"), "pi")
        self.assertEqual(live.classify_cmd("agent", "Cursor Agent"), "cursor")
        self.assertEqual(live.classify_cmd("claude", "Claude Code"), "claude-code")
        self.assertEqual(live.classify_cmd("bun /src/herm-tui/src/index.tsx"), "hermes")
        self.assertEqual(live.classify_cmd("codex --ask"), "codex")
        self.assertIsNone(live.classify_cmd("cursor-sdk-bridge"))
        self.assertIsNone(live.classify_cmd("/Applications/Cursor.app/Contents/MacOS/Cursor"))
        self.assertIsNone(live.classify_cmd("/opt/foo/codex-helper-worker"))
        self.assertIsNone(live.classify_cmd("zsh", "cxis"))

    def test_state(self) -> None:
        self.assertEqual(live.classify_state("waiting next @steer"), "idle")
        self.assertEqual(live.classify_state("Thinking about the patch"), "busy")
        self.assertEqual(live.classify_state("Compacting context"), "compact")
        self.assertEqual(live.classify_state(""), "idle")

    def test_redact(self) -> None:
        self.assertIn("[redacted]", live.redact("token sk-abc12345xyz and done"))
        self.assertEqual(live.last_activity("a\n───\nb now"), "b now")


class PsAndTmux(unittest.TestCase):
    def test_parse_ps(self) -> None:
        table = live.parse_ps_table("  10  1 zsh\n  11 10 pi --model x\n  12 11 cursor-sdk-bridge\n")
        self.assertEqual(table["11"]["ppid"], "10")
        kids = live.walk_children("10", table)
        cmds = {k["cmd"] for k in kids}
        self.assertIn("pi --model x", cmds)

    def test_parse_panes(self) -> None:
        panes = live.parse_tmux_panes("atop:0.1\t10\tpi\tπ\t/tmp/x\n")
        self.assertEqual(panes[0]["target"], "atop:0.1")
        self.assertEqual(panes[0]["cwd"], "/tmp/x")


class Layers(unittest.TestCase):
    def test_layer_status_from_fake_home(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            h = Path(raw)
            (h / ".pi/agent/skills/a-top").mkdir(parents=True)
            (h / ".pi/agent/skills/aos").mkdir(parents=True)
            (h / ".pi/agent/jobs").mkdir(parents=True)
            (h / ".codex/skills").mkdir(parents=True)
            rows = {r["id"]: r for r in live.layer_rows(h)}
            self.assertEqual(rows["a-top"]["status"], "ok")
            self.assertEqual(rows["aos"]["status"], "ok")
            self.assertEqual(rows["handoff"]["status"], "missing")
            self.assertEqual(rows["job-bus"]["status"], "ok")
            self.assertEqual(rows["codex-home"]["status"], "warn")
            data = live.collect(h, include_orphans=False)
            self.assertEqual(data["schema"], "atop.live.v1")
            self.assertIn(data["counts"]["layers_ok"], range(1, 20))
            md = live.render_markdown(data)
            self.assertIn("## layers", md)
            self.assertIn("## sessions", md)
            payload = json.loads(json.dumps(data))
            self.assertEqual(payload["schema"], "atop.live.v1")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
