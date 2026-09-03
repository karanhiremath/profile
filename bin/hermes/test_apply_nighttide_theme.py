#!/usr/bin/env python3
"""Unit tests for apply-nighttide-theme host/profile selection."""
from __future__ import annotations

import importlib.machinery
import json
import unittest
from pathlib import Path

mod = importlib.machinery.SourceFileLoader(
    "apply_nighttide_theme",
    str(Path(__file__).with_name("apply-nighttide-theme")),
).load_module()


class HostThemeTests(unittest.TestCase):
    def test_host_map(self) -> None:
        self.assertEqual(mod.host_cos_theme("karans-macbook-pro-1"), "nighttide-violet")
        self.assertEqual(mod.host_cos_theme("khire-mac-mini"), "nighttide-teal")
        self.assertEqual(mod.host_cos_theme("mac-mbp-13"), "nighttide-blue")
        self.assertEqual(mod.host_cos_theme("omarchy-mbp-13"), "nighttide-amber")
        self.assertEqual(mod.host_cos_theme("qemu-omarchy"), "nighttide-green")
        self.assertEqual(mod.host_cos_theme("omarchy-desktop"), "nighttide-green")
        self.assertEqual(mod.host_cos_theme("unknown-box"), "nighttide-violet")

    def test_work_vs_cos_homes(self) -> None:
        self.assertTrue(mod.is_work_home(Path("/tmp/hermes-agents/chief-of-staff-work")))
        self.assertFalse(mod.is_cos_home(Path("/tmp/hermes-agents/chief-of-staff-work")))
        self.assertTrue(mod.is_cos_home(Path("/tmp/hermes-agents/chief-of-staff")))
        self.assertTrue(mod.is_cos_home(Path("/tmp/hermes-agents/chief-of-staff/profiles/chief-of-staff")))
        self.assertFalse(mod.is_work_home(Path("/tmp/hermes-agents/chief-of-staff")))

    def test_variant_names(self) -> None:
        for name in (
            "nighttide-violet",
            "nighttide-teal",
            "nighttide-blue",
            "nighttide-amber",
            "nighttide-green",
            "nighttide-ember",
        ):
            self.assertIn(name, mod.THEME_VARIANTS)

    def test_cos_surfaces_are_transparent(self) -> None:
        body = json.loads(mod.theme_json("nighttide-teal"))
        self.assertEqual(body["defs"]["ntBg0"], "transparent")
        self.assertEqual(body["theme"]["background"]["dark"], "ntBg0")
        self.assertEqual(body["defs"]["ntAccent"], mod.TEAL)

    def test_fork_manifest_insert(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "manifest.ts"
            manifest.write_text(
                'export const PREVIEW = {\n'
                '  "nighttide-violet": { primary: "#64ba9a", accent: "#c792ea", background: "#2e3d4e" },\n'
                '};\n'
            )
            mod.ensure_fork_manifest(manifest)
            text = manifest.read_text()
            self.assertIn('"nighttide-teal":', text)
            self.assertIn('"nighttide-violet":', text)


if __name__ == "__main__":
    unittest.main()
