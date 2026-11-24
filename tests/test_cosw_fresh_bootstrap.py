from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin/hermes/hermes_agents.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_agents_fresh", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Keep sibling import discovery local, including any home-bound globals in
    # an alias_seat module previously imported by another test.
    with patch.object(sys, "path", sys.path.copy()), patch.dict(sys.modules):
        sys.modules.pop("alias_seat", None)
        spec.loader.exec_module(module)
    return module


class FreshCoswBootstrapTest(unittest.TestCase):
    def test_fresh_materialization_injects_dispatch_contract_and_safe_docker_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_home = root / "home"
            fake_home.mkdir()
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "chief-of-staff-work.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": "chief-of-staff-work",
                        "tts": {"enabled": False},
                        "stt": {"enabled": False},
                        "toolsets": ["terminal", "file"],
                        "persona": "Generic work dispatcher.",
                    }
                )
            )
            appendix = root / "dispatch.md"
            appendix.write_text("Run `cosw-hostctl bootstrap`, then use `cosw-hostctl dispatch-pm`.\n")
            pi_agent = root / "pi-agent"
            pi_agent.mkdir()
            (pi_agent / "auth.json").write_text('{}\n')
            main_home = fake_home / ".hermes"
            main_home.mkdir()
            (main_home / "auth.json").write_text('{}\n')
            # Real skill linking must only target temporary fixture sources.
            script_dir = root / "tooling/bin/hermes"
            script_dir.mkdir(parents=True)
            skill = root / "tooling/skills/pi/fixture-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("Fixture skill\n")

            ambient = root / "ambient"
            ambient.mkdir()
            for relative, content in {
                ".hermes/.env": "CURSOR_API_KEY=ambient_cursor\nTOGETHER_API_KEY=ambient_together\n",
                ".cursor/agent.env": "CURSOR_API_KEY=ambient_cursor\n",
                ".pi/agent/auth.json": '{"cursor": {"key": "ambient_cursor"}}\n',
                ".local/share/hermes-secrets/cursor-api-key": "ambient_cursor\n",
                "persona.md": "ambient persona must not be appended\n",
            }.items():
                path = ambient / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            ambient_snapshot = {
                path.relative_to(ambient): path.read_bytes()
                for path in ambient.rglob("*") if path.is_file()
            }
            poisoned = {key: str(ambient) for key in (
                "HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
                "AGENT_SHARED_HOME", "HERMES_SHARED_PEOPLE_HOME", "HERMES_AGENTS_DATA_HOME",
                "HERMES_HOME", "PI_AGENT_DIR", "HERMES_AGENT_PROFILE_PATH",
                "HERMES_AGENT_PROFILE_DIR", "HERMES_PROJECT_REGISTRY_PATH",
                "HERMES_PROJECT_REGISTRY_DIRS",
            )}
            poisoned.update({
                "PI_AGENT_DIR": str(ambient / ".pi/agent"),
                "CURSOR_API_KEY": "ambient_cursor", "TOGETHER_API_KEY": "ambient_together",
                "OPENAI_API_KEY": "ambient_openai", "ANTHROPIC_API_KEY": "ambient_anthropic",
                "CARTESIA_API_KEY": "ambient_cartesia", "HERMES_SECRETS_REFRESH": "1",
                "HERMES_PERSONA_APPEND_FILE": str(ambient / "persona.md"),
                "HERMES_AGENT_LLM_PROVIDER": "ambient", "HERMES_AGENT_LLM_MODEL": "ambient",
                "HERMES_AGENT_LLM_THINKING": "low", "AGENTIC_HOST_CLASS": "ambient",
                "AGENTIC_COSW_PLANE": "ambient", "USER": "ambient-user", "LOGNAME": "ambient-user",
                "AWS_PROFILE": "ambient_profile", "HERMES_DOCKER_BINARY": "ambient_docker",
            })
            env = {
                "HOME": str(fake_home),
                "XDG_DATA_HOME": str(root / "fresh-data"),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "PI_AGENT_DIR": str(pi_agent),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
                "HERMES_PROJECT_REGISTRY_PATH": str(root / "registry"),
                "HERMES_PROJECT_REGISTRY_DIRS": str(root / "registry"),
                "AGENTIC_HOST_CLASS": "work",
                "AGENTIC_COSW_PLANE": "fixture",
                "USER": "", "LOGNAME": "",
                "HERMES_AGENT_TERMINAL_BACKEND": "docker",
                "TERMINAL_CWD": "/workspace",
                "TERMINAL_DOCKER_VOLUMES": json.dumps([f"{root / 'host/socket'}:/run/hermes-manager:ro"]),
                "TERMINAL_DOCKER_EXTRA_ARGS": json.dumps(["--userns=keep-id:uid=1000,gid=1000"]),
                "TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES": "true",
                "TERMINAL_DOCKER_ENV": json.dumps({
                    "COSW_HOST_CONTROL_SOCKET": "/run/hermes-manager/manager.sock",
                    "HERMES_SANDBOX_ID": "chief-of-staff-work",
                }),
                "HERMES_PERSONA_APPEND_FILE": str(appendix),
            }
            with patch.dict(os.environ, poisoned, clear=False), patch.dict(os.environ, env, clear=True):
                # The explicit class and profile path must bypass host-env.sh.
                with patch("subprocess.check_output", side_effect=AssertionError("host probe forbidden")):
                    module = load_module()
                self.assertEqual(module.MAIN_HOME, main_home)
                self.assertEqual(module._SECRETS_DIR, fake_home / ".local/share/hermes-secrets")
                self.assertEqual(module._CURSOR_META, module._SECRETS_DIR / "cursor.meta.json")
                self.assertEqual(module._DEFAULT_PROFILE_DIRS, [
                    fake_home / "src/karan.hiremath/agentic/hermes/profiles",
                    fake_home / "src/hermes/profiles",
                    MODULE_PATH.parent / "profiles",
                ])
                self.assertEqual(module.profile_path(), [profiles])
                self.assertFalse(module._secrets_refresh_requested())
                self.assertIsNone(module._shared_people_root())
                self.assertEqual(module._data_home(), root / "fresh-data/hermes-agents")
                with (
                    patch.object(module, "SCRIPT_DIR", script_dir),
                    patch.object(module, "PLUGIN_DIR", script_dir / "plugins/cartesia"),
                    patch.object(module, "TEMPLATE_PATH", script_dir / "profiles/TEMPLATE.yaml"),
                    patch.object(module, "_keychain_get_cursor_key", return_value=None),
                    patch.object(module, "_keychain_set_cursor_key", side_effect=AssertionError("keychain write forbidden")),
                    patch.object(module, "_cursor_api_key_from_op", side_effect=AssertionError("1Password lookup forbidden")),
                ):
                    home = module.materialize("chief-of-staff-work")
                self.assertTrue(home.is_dir())
                self.assertEqual(home, root / "fresh-data/hermes-agents/chief-of-staff-work")
                runtime = home / "profiles/chief-of-staff-work"
                for destination in (home, runtime, module.MAIN_HOME, module._SECRETS_DIR):
                    self.assertTrue(destination.resolve().is_relative_to(root.resolve()), destination)
                for path in home.rglob("*"):
                    if path.is_symlink():
                        self.assertTrue(path.resolve().is_relative_to(root.resolve()), path)
                    elif path.is_file():
                        self.assertNotIn(b"ambient_", path.read_bytes(), path)
                        self.assertNotIn(b"ambient persona", path.read_bytes(), path)
                for destination in (home, runtime):
                    self.assertEqual((destination / "auth.json").resolve(), (main_home / "auth.json").resolve())
                    self.assertEqual((destination / "skills/fixture-skill").resolve(), skill.resolve())
                    env_file = module._read_env_file(destination / ".env")
                    self.assertNotIn("CURSOR_API_KEY", env_file)
                    self.assertNotIn("TOGETHER_API_KEY", env_file)
                    self.assertNotIn("AWS_PROFILE", env_file)
                    self.assertNotIn("HERMES_DOCKER_BINARY", env_file)
                self.assertFalse((main_home / ".env").exists())
                self.assertFalse((fake_home / ".cursor/agent.env").exists())
                self.assertFalse(module._file_cache_path().exists())
                self.assertEqual({
                    path.relative_to(ambient): path.read_bytes()
                    for path in ambient.rglob("*") if path.is_file()
                }, ambient_snapshot)

                config = yaml.safe_load((home / "config.yaml").read_text())
                self.assertEqual(config["model"], {"provider": "openai-codex", "default": "gpt-5.5"})
                self.assertNotIn("reasoning_effort", config.get("agent", {}))
                terminal = config["terminal"]
                self.assertEqual(terminal["cwd"], "/workspace")
                self.assertTrue(terminal["docker_persist_across_processes"])
                self.assertEqual(terminal["docker_extra_args"], ["--userns=keep-id:uid=1000,gid=1000"])
                self.assertEqual(terminal["docker_volumes"], [f"{root / 'host/socket'}:/run/hermes-manager:ro"])
                self.assertEqual(
                    terminal["docker_env"]["COSW_HOST_CONTROL_SOCKET"],
                    "/run/hermes-manager/manager.sock",
                )
                soul = (home / "SOUL.md").read_text()
                self.assertIn("Generic work dispatcher", soul)
                self.assertIn("cosw-hostctl bootstrap", soul)
                self.assertIn("cosw-hostctl dispatch-pm", soul)
                self.assertEqual((runtime / "SOUL.md").read_text(), soul)


if __name__ == "__main__":
    unittest.main()
