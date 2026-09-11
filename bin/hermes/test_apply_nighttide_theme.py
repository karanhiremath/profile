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
        self.assertEqual(mod.host_cos_theme("personal-mini"), "nighttide-teal")
        self.assertEqual(mod.host_cos_theme("mac-mbp-13"), "nighttide-blue")
        self.assertEqual(mod.host_cos_theme("omarchy-mbp-13"), "nighttide-amber")
        self.assertEqual(mod.host_cos_theme("qemu-omarchy"), "nighttide-green")
        self.assertEqual(mod.host_cos_theme("omarchy-desktop"), "nighttide-green")
        self.assertEqual(mod.host_cos_theme("omarchy"), "nighttide-green")
        self.assertEqual(mod.host_cos_theme("tc2"), "nighttide-violet")
        self.assertEqual(mod.host_cos_theme("work-mbp"), "nighttide-violet")
        self.assertEqual(mod.host_cos_theme("unknown-box"), "nighttide-violet")

    def test_work_vs_cos_homes(self) -> None:
        self.assertTrue(mod.is_work_home(Path("/tmp/hermes-agents/chief-of-staff-work")))
        self.assertFalse(mod.is_cos_home(Path("/tmp/hermes-agents/chief-of-staff-work")))
        self.assertTrue(mod.is_cos_home(Path("/tmp/hermes-agents/chief-of-staff")))
        self.assertTrue(mod.is_cos_home(Path("/tmp/hermes-agents/chief-of-staff/profiles/chief-of-staff")))
        self.assertFalse(mod.is_work_home(Path("/tmp/hermes-agents/chief-of-staff")))

    def test_dreamw_vs_cosw(self) -> None:
        cosw = Path("/tmp/hermes-agents/chief-of-staff-work")
        dreamw = Path("/tmp/hermes-agents/dreamw")
        hdream = Path("/tmp/.hermes/profiles/hdream")
        self.assertEqual(mod.profile_class(cosw), "work")
        self.assertEqual(mod.profile_class(dreamw), "dream")
        self.assertEqual(mod.profile_class(hdream), "dream")
        self.assertEqual(mod.theme_for_home(cosw), "nighttide-ember")
        self.assertEqual(mod.theme_for_home(dreamw), "nighttide-cyan")
        self.assertEqual(mod.resolve_profile_class("dreamw"), "dream")
        self.assertEqual(mod.resolve_profile_class("cosw"), "work")

    def test_variant_names(self) -> None:
        for name in (
            "nighttide-violet",
            "nighttide-teal",
            "nighttide-blue",
            "nighttide-amber",
            "nighttide-green",
            "nighttide-ember",
            "nighttide-cyan",
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

    def test_theme_override_is_one_shot(self) -> None:
        home = Path("/tmp/hermes-agents/chief-of-staff-work")
        self.assertEqual(
            mod.theme_for_home(home, theme_override="nighttide-cyan"),
            "nighttide-cyan",
        )
        self.assertEqual(mod.theme_for_home(home), "nighttide-ember")

    def test_set_default_pin(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "dreamw"
            theme = mod.merge_pref(
                home,
                theme_override="nighttide-red",
                set_default=True,
                eikon="nous",
            )
            self.assertEqual(theme, "nighttide-red")
            data = json.loads((home / "herm" / "tui.json").read_text())
            self.assertEqual(data["theme"], "nighttide-red")
            self.assertEqual(data[mod.PIN_KEY], "nighttide-red")
            self.assertEqual(data["eikon"], "nous")
            self.assertEqual(mod.theme_for_home(home), "nighttide-red")
            self.assertEqual(mod.theme_for_home(home, force=True), "nighttide-cyan")


if __name__ == "__main__":
    unittest.main()
