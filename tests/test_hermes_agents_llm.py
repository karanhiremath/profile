from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin/hermes/hermes_agents.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_agents_llm", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HermesAgentsLlmRenderTest(unittest.TestCase):
    def test_render_passes_cursor_model_and_thinking_to_hermes_config(self):
        module = load_module()
        cfg = module._render_config(
            {
                "tts": {"enabled": False},
                "stt": {"enabled": False},
                "toolsets": ["terminal", "file"],
                "llm": {
                    "provider": "cursor",
                    "model": "grok-4.6:fast",
                    "thinking": "xhigh",
                },
            }
        )
        self.assertEqual(cfg["model"]["provider"], "cursor")
        self.assertEqual(cfg["model"]["default"], "grok-4.6:fast")
        self.assertEqual(cfg["agent"]["reasoning_effort"], "xhigh")

    def test_materialize_writes_thinking_and_syncs_cursor_key(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "chief-of-staff-work.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": "chief-of-staff-work",
                        "tts": {"enabled": False},
                        "stt": {"enabled": False},
                        "toolsets": ["terminal"],
                        "llm": {
                            "provider": "cursor",
                            "model": "grok-4.6:fast",
                            "thinking": "xhigh",
                        },
                    }
                )
            )
            env = {
                "XDG_DATA_HOME": str(root / "data"),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
                "CURSOR_API_KEY": "cursor_test_key",
            }
            with patch.dict(os.environ, env, clear=False):
                home = module.materialize("chief-of-staff-work")
            config = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(config["model"]["provider"], "cursor")
            self.assertEqual(config["model"]["default"], "grok-4.6:fast")
            self.assertEqual(config["agent"]["reasoning_effort"], "xhigh")
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("CURSOR_API_KEY"), "cursor_test_key")

    def test_materialize_syncs_cursor_key_from_pi_auth(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "chief-of-staff-work.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": "chief-of-staff-work",
                        "tts": {"enabled": False},
                        "stt": {"enabled": False},
                        "toolsets": ["terminal"],
                        "llm": {
                            "provider": "cursor",
                            "model": "grok-4.6:fast",
                            "thinking": "xhigh",
                        },
                    }
                )
            )
            pi_agent = root / "pi-agent"
            pi_agent.mkdir()
            (pi_agent / "auth.json").write_text(
                '{"cursor": {"type": "api_key", "key": "pi_cursor_test_key"}}\n'
            )
            env = {
                "XDG_DATA_HOME": str(root / "data"),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
                "PI_AGENT_DIR": str(pi_agent),
            }
            with patch.dict(os.environ, env, clear=False):
                os.environ.pop("CURSOR_API_KEY", None)
                home = module.materialize("chief-of-staff-work")
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("CURSOR_API_KEY"), "pi_cursor_test_key")

    def test_llm_env_overrides_and_local_backend_clears_docker_env(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "chief-of-staff-work.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": "chief-of-staff-work",
                        "tts": {"enabled": False},
                        "stt": {"enabled": False},
                        "toolsets": ["terminal"],
                        "llm": {
                            "provider": "cursor",
                            "model": "grok-4.6:fast",
                            "thinking": "xhigh",
                        },
                    }
                )
            )
            home = root / "data" / "hermes-agents" / "chief-of-staff-work"
            home.mkdir(parents=True)
            (home / ".env").write_text(
                "TERMINAL_ENV=docker\nTERMINAL_DOCKER_IMAGE=stale\nCURSOR_API_KEY=keep\n"
            )
            env = {
                "XDG_DATA_HOME": str(root / "data"),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
                "HERMES_AGENT_TERMINAL_BACKEND": "local",
                "HERMES_AGENT_LLM_PROVIDER": "openai-codex",
                "HERMES_AGENT_LLM_MODEL": "gpt-5.5",
                "TERMINAL_CWD": str(root / "work"),
            }
            with patch.dict(os.environ, env, clear=False):
                home = module.materialize("chief-of-staff-work")
            config = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(config["model"]["provider"], "openai-codex")
            self.assertEqual(config["model"]["default"], "gpt-5.5")
            self.assertEqual(config["terminal"]["backend"], "local")
            self.assertEqual(config["terminal"]["cwd"], str(root / "work"))
            self.assertNotIn("docker_image", config["terminal"])
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("TERMINAL_ENV"), "local")
            self.assertNotIn("TERMINAL_DOCKER_IMAGE", env_file)


if __name__ == "__main__":
    unittest.main()
