#!/usr/bin/env python3
"""Clone --lane profile YAML next to the base. No live Cos/tmux attach."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import hermes_agents as ha


class EnsureLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.profiles = Path(self.tmp.name) / "profiles"
        self.profiles.mkdir()
        (self.profiles / "chief-of-staff.yaml").write_text(
            "name: chief-of-staff\nsurface: tui\n",
            encoding="utf-8",
        )
        self.saved = os.environ.get("HERMES_AGENT_PROFILE_PATH")
        os.environ["HERMES_AGENT_PROFILE_PATH"] = str(self.profiles)

    def tearDown(self) -> None:
        if self.saved is None:
            os.environ.pop("HERMES_AGENT_PROFILE_PATH", None)
        else:
            os.environ["HERMES_AGENT_PROFILE_PATH"] = self.saved
        self.tmp.cleanup()

    def test_ensure_lane_clones_once_and_renames(self) -> None:
        name = ha.ensure_lane_profile("chief-of-staff", "o1")
        self.assertEqual(name, "chief-of-staff-o1")
        dst = self.profiles / "chief-of-staff-o1.yaml"
        self.assertTrue(dst.is_file())
        text = dst.read_text(encoding="utf-8")
        self.assertIn("name: chief-of-staff-o1", text)
        self.assertNotIn("name: chief-of-staff\n", text)
        first_mtime = dst.stat().st_mtime_ns
        again = ha.ensure_lane_profile("chief-of-staff", "o1")
        self.assertEqual(again, name)
        self.assertEqual(dst.stat().st_mtime_ns, first_mtime)

    def test_missing_base_fails(self) -> None:
        with self.assertRaises(SystemExit):
            ha.ensure_lane_profile("chief-of-staff-work", "o1")


if __name__ == "__main__":
    unittest.main()
