#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from schema import load_bundle  # noqa: E402
from voice import filter_transcript, timeout_speech, world_brief  # noqa: E402


def bundle():
    return load_bundle(ROOT / "config" / "aos" / "policy", Path(tempfile.mkdtemp()))


class VoiceHarnessTests(unittest.TestCase):
    def test_filter_stall(self):
        tick = filter_transcript("I'm working on it.", bundle=bundle(), world={"speakable": "Holding from inventory."})
        self.assertNotIn("working on it", tick["speech"].lower())
        self.assertEqual(tick["source"], "rewrite")

    def test_timeout_never_errors(self):
        tick = timeout_speech(world={"speakable": "Atop shows 2 live herm buffers. Continuing from there."})
        self.assertEqual(tick["source"], "timeout")
        self.assertNotIn("did not reply", tick["speech"].lower())
        self.assertIn("Atop", tick["speech"])

    def test_world_brief_speakable(self):
        brief = world_brief(
            [
                {"id": "herm-1", "harness": "herm", "live": True, "modified": True, "path": "/tmp/herm-1.md"},
                {"id": "pi-1", "harness": "pi", "live": True, "modified": False, "path": "/tmp/pi-1.md"},
            ]
        )
        self.assertEqual(brief["live"], 2)
        self.assertEqual(brief["modified"], 1)
        self.assertNotIn("did not reply", brief["speakable"].lower())
        self.assertNotIn("i'm working on it", brief["speakable"].lower())
        self.assertIn("live", brief["speakable"])


if __name__ == "__main__":
    unittest.main()
