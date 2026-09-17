#!/usr/bin/env python3
"""TUI-owned config/theme must survive agents-up rematerialize."""
from __future__ import annotations

import importlib.machinery
import json
import tempfile
import unittest
from pathlib import Path

mod = importlib.machinery.SourceFileLoader(
    "hermes_agents",
    str(Path(__file__).with_name("hermes_agents.py")),
).load_module()


class PersistPrefsTests(unittest.TestCase):
    def test_nighttide_pin_keeps_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tui.json"
            path.write_text(json.dumps({
                "theme": "nighttide-teal",
                "themeMode": "dark",
                "nighttideDefault": "nighttide-teal",
                "eikon": "nous",
            }) + "\n")
            mod._merge_json_file(path, {
                "theme": "nighttide-violet",
                "themeMode": "dark",
                "eikon": "nous",
                "identity": {"label": "CoS"},
            })
            data = json.loads(path.read_text())
            self.assertEqual(data["theme"], "nighttide-teal")
            self.assertEqual(data["nighttideDefault"], "nighttide-teal")
            self.assertEqual(data["identity"]["label"], "CoS")

    def test_force_overwrites_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tui.json"
            path.write_text(json.dumps({
                "theme": "nighttide-teal",
                "nighttideDefault": "nighttide-teal",
            }) + "\n")
            mod._merge_json_file(path, {"theme": "nighttide-violet"}, force=True)
            data = json.loads(path.read_text())
            self.assertEqual(data["theme"], "nighttide-violet")

    def test_config_keeps_tui_model_and_toolsets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "model:\n  provider: cursor\n  default: claude-opus-5\n"
                "toolsets:\n- terminal\n- skills\n"
                "display:\n  busy_input_mode: steer\n"
            )
            cfg = {
                "model": {"provider": "cursor", "default": "grok-4.6:fast"},
                "toolsets": ["terminal", "file"],
                "display": {"thinking_mode": "full"},
            }
            out = mod._merge_existing_config(path, cfg)
            self.assertEqual(out["model"]["default"], "claude-opus-5")
            self.assertEqual(out["toolsets"], ["terminal", "skills", "file"])
            self.assertEqual(out["display"], {"busy_input_mode": "steer"})

    def test_config_unions_voice_plugin_and_tts_toolset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "toolsets:\n- terminal\n- skills\n"
                "plugins:\n  enabled:\n  - eikon\n"
                "stt:\n  enabled: false\n"
            )
            cfg = {
                "toolsets": ["terminal", "file", "tts"],
                "plugins": {"enabled": ["cartesia"]},
                "stt": {"enabled": True, "provider": "cartesia"},
            }
            out = mod._merge_existing_config(path, cfg)
            self.assertEqual(out["toolsets"], ["terminal", "skills", "file", "tts"])
            self.assertEqual(out["plugins"]["enabled"], ["cartesia", "eikon"])
            self.assertTrue(out["stt"]["enabled"])

    def test_force_config_uses_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("model:\n  default: claude-opus-5\n")
            cfg = {"model": {"default": "grok-4.6:fast"}, "toolsets": ["file"]}
            out = mod._merge_existing_config(path, cfg, force=True)
            self.assertEqual(out["model"]["default"], "grok-4.6:fast")

    def test_autonomous_family_merges_optional_grok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled = root / "bundled"
            optional = root / "optional"
            dest = root / "skills" / "autonomous-ai-agents"
            (bundled / "codex").mkdir(parents=True)
            (bundled / "codex" / "SKILL.md").write_text("codex\n")
            (optional / "grok").mkdir(parents=True)
            (optional / "grok" / "SKILL.md").write_text("grok\n")
            dest.parent.mkdir(parents=True)
            dest.symlink_to(bundled)
            mod._link_autonomous_family(dest, bundled, optional)
            self.assertTrue(dest.is_dir())
            self.assertFalse(dest.is_symlink())
            self.assertTrue((dest / "codex").is_symlink())
            self.assertTrue((dest / "grok").is_symlink())

    def test_profile_env_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "token"
            secret.write_text("lin_api_test\n")
            secret.chmod(0o600)
            updates = mod.profile_env_updates({
                "env": {
                    "LINEAR_TOKEN_FILE": str(secret),
                    "LINEAR_TEAM": "KH",
                },
                "env_from_file": {"LINEAR_API_KEY": str(secret)},
            })
            self.assertEqual(updates["LINEAR_API_KEY"], "lin_api_test")
            self.assertEqual(updates["LINEAR_TEAM"], "KH")
            self.assertEqual(updates["LINEAR_TOKEN_FILE"], str(secret))


if __name__ == "__main__":
    unittest.main()
