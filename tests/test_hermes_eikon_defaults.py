"""Avatar preferences and packages survive rematerialization and sibling seats."""
from __future__ import annotations

import importlib.machinery
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# hermes_agents adds its sibling directory for alias_seat; keep that import
# path local so later unittest discovery resolves modules from tests/.
with patch.object(sys, "path", sys.path.copy()):
    ha = importlib.machinery.SourceFileLoader(
        "hermes_eikon_defaults", str(ROOT / "bin/hermes/hermes_agents.py"),
    ).load_module()


class EikonDefaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "agents"
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"HERMES_AGENTS_DATA_HOME": str(self.data)}, clear=True).start()
        patch.object(ha, "MAIN_HOME", self.root / ".hermes").start()
        patch.object(Path, "home", return_value=self.root).start()

    def _pref(self, home: Path, eikon: str) -> Path:
        path = home / "herm/tui.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"eikon": eikon, "lastSessionId": "do-not-inherit"}))
        return path

    def test_rematerialize_preserves_custom_avatar(self) -> None:
        path = self._pref(self.root, "ares")
        ha._merge_json_file(path, {"eikon": "nous", "theme": "nighttide-ember"})
        data = json.loads(path.read_text())
        self.assertEqual(data["eikon"], "ares")
        self.assertEqual(data["lastSessionId"], "do-not-inherit")

    def test_force_and_fresh_home_accept_yaml_avatar(self) -> None:
        path = self._pref(self.root, "ares")
        ha._merge_json_file(path, {"eikon": "mono"}, force=True)
        self.assertEqual(ha._eikon_preference(self.root), "mono")
        fresh = self.root / "fresh"
        ha._merge_json_file(fresh / "herm/tui.json", {"eikon": "ares"})
        self.assertEqual(ha._eikon_preference(fresh), "ares")

    def test_sibling_inherits_runtime_avatar_over_root(self) -> None:
        base = self.data / "chief-of-staff-work"
        self._pref(base, "nous")
        self._pref(base / "profiles/chief-of-staff-work", "ares")
        self.assertEqual(ha._inherited_eikon("chief-of-staff-work-a1"), "ares")
        self.assertFalse((self.data / "chief-of-staff-work-a1").exists())

    def test_nested_sibling_prefers_lane_then_family(self) -> None:
        self._pref(self.data / "chief-of-staff-work", "ares")
        self.assertEqual(ha._inherited_eikon("chief-of-staff-work-o1-a1"), "ares")
        self._pref(self.data / "chief-of-staff-work-o1", "mono")
        self.assertEqual(ha._inherited_eikon("chief-of-staff-work-o1-a1"), "mono")

    def test_families_do_not_leak_and_base_is_not_a_sibling(self) -> None:
        self._pref(self.data / "chief-of-staff", "nous")
        self.assertIsNone(ha._inherited_eikon("chief-of-staff-work-a1"))
        self.assertIsNone(ha._inherited_eikon("chief-of-staff-work"))
        self.assertIsNone(ha._inherited_eikon("unknown-a1"))

    def test_invalid_preferences_are_ignored(self) -> None:
        path = self._pref(self.root, "ares")
        for raw in ("{", "[]", '{"eikon": false}', '{"eikon": ""}'):
            path.write_text(raw)
            self.assertIsNone(ha._eikon_preference(self.root))

    def test_selected_package_copies_into_both_isolated_homes(self) -> None:
        base = self.data / "chief-of-staff-work/profiles/chief-of-staff-work"
        source = base / "eikons/ares"
        source.mkdir(parents=True)
        (source / "ares.eikon").write_text("test-avatar-bytes")
        (source / "base.png").write_bytes(b"test-media")
        root = self.data / "chief-of-staff-work-a1"
        runtime = root / "profiles/chief-of-staff-work-a1"
        self.assertEqual(ha._find_installed_eikon("ares"), source)
        ha._sync_eikon_into_homes("ares", root, runtime)
        for home in (root, runtime):
            self.assertEqual((home / "eikons/ares/ares.eikon").read_text(), "test-avatar-bytes")
            self.assertEqual((home / "eikons/ares/base.png").read_bytes(), b"test-media")

    def test_materialize_inherits_and_installs_effective_avatar_without_auth(self) -> None:
        base = self.data / "chief-of-staff-work/profiles/chief-of-staff-work"
        self._pref(base, "ares")
        for name in ("ares", "mono"):
            source = base / "eikons" / name
            source.mkdir(parents=True)
            (source / f"{name}.eikon").write_text(name + "-bytes")
        profile = {"name": "chief-of-staff-work-a1"}
        with (
            patch.object(ha, "load_profile", return_value=profile),
            patch.object(ha, "voice_on", return_value=False),
            patch.object(ha, "resolve_base_url", return_value=None),
            patch.object(ha, "_render_config", return_value={"model": {"provider": "test"}}),
            patch.object(ha, "_ensure_skill_links"),
            patch.object(ha, "_upsert_env"),
            patch.object(ha, "_resolve_env", side_effect=AssertionError("auth must stay mocked")),
        ):
            root = ha.materialize(profile["name"])
            runtime = root / "profiles" / profile["name"]
            self.assertEqual(ha._eikon_preference(runtime), "ares")
            self.assertEqual((runtime / "eikons/ares/ares.eikon").read_text(), "ares-bytes")
            self._pref(runtime, "mono")
            profile["herm"] = {"preferences": {"eikon": "nous"}}
            ha.materialize(profile["name"])
            self.assertEqual(ha._eikon_preference(runtime), "mono")
            self.assertEqual((runtime / "eikons/mono/mono.eikon").read_text(), "mono-bytes")
            self.assertFalse((runtime / "auth.json").exists())

    def test_herm_checkout_catalog_is_a_fallback(self) -> None:
        source = self.root / "src/herm/node_modules/eikon/eikons/ares"
        source.mkdir(parents=True)
        (source / "ares.eikon").write_text("test-avatar-bytes")
        self.assertEqual(ha._find_installed_eikon("ares"), source)


if __name__ == "__main__":
    unittest.main()
