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

    def test_materialize_syncs_together_key_from_pi_auth(self):
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
                        "providers": {
                            "together": {
                                "name": "Together",
                                "api": "https://api.together.ai/v1",
                                "key_env": "TOGETHER_API_KEY",
                                "transport": "chat_completions",
                            }
                        },
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
                '{"together": {"type": "api_key", "key": "pi_together_test_key"}}\n'
            )
            env = {
                "XDG_DATA_HOME": str(root / "data"),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
                "PI_AGENT_DIR": str(pi_agent),
            }
            with patch.dict(os.environ, env, clear=False):
                os.environ.pop("TOGETHER_API_KEY", None)
                home = module.materialize("chief-of-staff-work")
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("TOGETHER_API_KEY"), "pi_together_test_key")

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


def _write_router(profiles: Path, llm=None, fallback=None) -> None:
    router = {"name": "model-router", "tts": {"enabled": False}, "stt": {"enabled": False}}
    if llm is not None:
        router["llm"] = llm
    if fallback is not None:
        router["fallback_model"] = fallback
    (profiles / "model-router.yaml").write_text(yaml.safe_dump(router))


def _write_seat(profiles: Path, llm=None) -> None:
    seat = {"name": "chief-of-staff-work", "tts": {"enabled": False}, "stt": {"enabled": False}, "toolsets": ["terminal"]}
    if llm is not None:
        seat["llm"] = llm
    (profiles / "chief-of-staff-work.yaml").write_text(yaml.safe_dump(seat))


class HermesAgentsModelRouterTest(unittest.TestCase):
    ROUTER_LLM = {"provider": "cursor", "model": "grok-4.6:fast", "thinking": "xhigh"}
    ROUTER_CHAIN = [
        {"provider": "openai-codex", "model": "gpt-5.5"},
        {"provider": "openai-codex", "model": "gpt-5.6-luna"},
        {"provider": "openai-codex", "model": "gpt-5.6-terra"},
        {"provider": "openai-codex", "model": "gpt-5.6-sol"},
        {"provider": "cursor", "model": "grok-4.6:fast"},
    ]

    def test_router_fills_missing_llm_keys_and_installs_chain_excluding_primary(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            _write_router(profiles, llm=self.ROUTER_LLM, fallback=self.ROUTER_CHAIN)
            _write_seat(profiles, llm={"provider": "openai-codex", "model": "gpt-5.5"})
            with patch.dict(os.environ, {"HERMES_AGENT_PROFILE_PATH": str(profiles)}, clear=False):
                profile = module.load_profile("chief-of-staff-work")
            self.assertEqual(profile["llm"]["provider"], "openai-codex")
            self.assertEqual(profile["llm"]["model"], "gpt-5.5")
            self.assertEqual(profile["llm"]["thinking"], "xhigh")
            chain = profile["fallback_model"]
            self.assertEqual(chain[0], {"provider": "openai-codex", "model": "gpt-5.6-luna"})
            self.assertNotIn({"provider": "openai-codex", "model": "gpt-5.5"}, chain)
            self.assertIn({"provider": "cursor", "model": "grok-4.6:fast"}, chain)

    def test_router_llm_defaults_when_profile_has_no_llm(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            _write_router(profiles, llm=self.ROUTER_LLM, fallback=self.ROUTER_CHAIN)
            _write_seat(profiles)
            with patch.dict(os.environ, {"HERMES_AGENT_PROFILE_PATH": str(profiles)}, clear=False):
                profile = module.load_profile("chief-of-staff-work")
            self.assertEqual(profile["llm"]["provider"], "cursor")
            self.assertEqual(profile["llm"]["model"], "grok-4.6:fast")
            chain = profile["fallback_model"]
            self.assertNotIn({"provider": "cursor", "model": "grok-4.6:fast"}, chain)
            self.assertEqual(chain[0], {"provider": "openai-codex", "model": "gpt-5.5"})

    def test_profile_fallback_model_wins_over_router(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            _write_router(profiles, llm=self.ROUTER_LLM, fallback=self.ROUTER_CHAIN)
            _write_seat(
                profiles,
                llm={"provider": "cursor", "model": "grok-4.6:fast"},
            )
            # Re-write the seat with an explicit fallback_model to check precedence.
            seat_path = profiles / "chief-of-staff-work.yaml"
            seat = yaml.safe_load(seat_path.read_text())
            seat["fallback_model"] = [{"provider": "openai-codex", "model": "gpt-5.5"}]
            seat_path.write_text(yaml.safe_dump(seat))
            with patch.dict(os.environ, {"HERMES_AGENT_PROFILE_PATH": str(profiles)}, clear=False):
                profile = module.load_profile("chief-of-staff-work")
            self.assertEqual(profile["fallback_model"], [{"provider": "openai-codex", "model": "gpt-5.5"}])

    def test_missing_router_file_is_a_no_op(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            _write_seat(profiles, llm={"provider": "cursor", "model": "grok-4.6:fast"})
            with patch.dict(os.environ, {"HERMES_AGENT_PROFILE_PATH": str(profiles)}, clear=False):
                profile = module.load_profile("chief-of-staff-work")
            self.assertNotIn("fallback_model", profile)
            self.assertEqual(profile["llm"]["provider"], "cursor")

    def test_render_config_passes_fallback_chain_and_fails_closed(self):
        module = load_module()
        cfg = module._render_config(
            {
                "tts": {"enabled": False},
                "stt": {"enabled": False},
                "llm": dict(self.ROUTER_LLM),
                "fallback_model": [
                    {"provider": "openai-codex", "model": "gpt-5.5"},
                    {"provider": "openai-codex", "model": "gpt-5.6-sol"},
                ],
            }
        )
        self.assertEqual(
            cfg["fallback_model"],
            [
                {"provider": "openai-codex", "model": "gpt-5.5"},
                {"provider": "openai-codex", "model": "gpt-5.6-sol"},
            ],
        )
        with self.assertRaises(SystemExit):
            module._render_config(
                {
                    "tts": {"enabled": False},
                    "stt": {"enabled": False},
                    "fallback_model": [{"provider": "openai-codex"}],
                }
            )

    def test_materialize_writes_shared_fallback_chain_into_config(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            _write_router(profiles, llm=self.ROUTER_LLM, fallback=self.ROUTER_CHAIN)
            _write_seat(profiles, llm={"provider": "openai-codex", "model": "gpt-5.5"})
            env = {
                "XDG_DATA_HOME": str(root / "data"),
                "HERMES_AGENT_PROFILE_PATH": str(profiles),
            }
            with patch.dict(os.environ, env, clear=False):
                home = module.materialize("chief-of-staff-work")
            config = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(config["model"]["default"], "gpt-5.5")
            chain = config["fallback_model"]
            self.assertEqual(chain[0], {"provider": "openai-codex", "model": "gpt-5.6-luna"})
            self.assertNotIn({"provider": "openai-codex", "model": "gpt-5.5"}, chain)


if __name__ == "__main__":
    unittest.main()
