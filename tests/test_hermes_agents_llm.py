from __future__ import annotations

import importlib.util
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
    spec = importlib.util.spec_from_file_location("hermes_agents_llm", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # hermes_agents adds its sibling directory for alias_seat. Do not leave
    # that directory ahead of tests/ during full unittest discovery.
    with patch.object(sys, "path", sys.path.copy()), patch.dict(sys.modules):
        # A sibling imported by another test may also have home-bound globals.
        sys.modules.pop("alias_seat", None)
        spec.loader.exec_module(module)
    return module


class ContainedHermesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.fake_home = self.root / "home"
        self.fake_home.mkdir()
        self.fixture_profiles = self.root / "profiles"
        self.fixture_profiles.mkdir()
        self.pi_agent = self.root / "pi-agent"
        self.pi_agent.mkdir()

        # Seed conflicting but entirely fake operator state before clearing the
        # environment. Neither these files nor these overrides may win.
        self.ambient = self.root / "ambient"
        self.ambient.mkdir()
        ambient_files = {
            ".hermes/.env": "CURSOR_API_KEY=ambient_cursor\nTOGETHER_API_KEY=ambient_together\n",
            ".cursor/agent.env": "CURSOR_API_KEY=ambient_cursor\n",
            ".pi/agent/auth.json": '{"cursor": {"key": "ambient_cursor"}, "together": {"key": "ambient_together"}}\n',
            ".local/share/hermes-secrets/cursor-api-key": "ambient_cursor\n",
            "persona.md": "ambient persona must not be appended\n",
        }
        for relative, content in ambient_files.items():
            path = self.ambient / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.ambient_snapshot = {
            path.relative_to(self.ambient): path.read_bytes()
            for path in self.ambient.rglob("*") if path.is_file()
        }
        poisoned = {key: str(self.ambient) for key in (
            "HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
            "AGENT_SHARED_HOME", "HERMES_SHARED_PEOPLE_HOME", "HERMES_AGENTS_DATA_HOME",
            "HERMES_AGENT_PROFILE_PATH", "HERMES_AGENT_PROFILE_DIR",
            "HERMES_PROJECT_REGISTRY_PATH", "HERMES_PROJECT_REGISTRY_DIRS",
            "HERMES_HOME", "PI_AGENT_DIR",
        )}
        poisoned.update({
            "PI_AGENT_DIR": str(self.ambient / ".pi/agent"),
            "CURSOR_API_KEY": "ambient_cursor", "TOGETHER_API_KEY": "ambient_together",
            "OPENAI_API_KEY": "ambient_openai", "ANTHROPIC_API_KEY": "ambient_anthropic",
            "CARTESIA_API_KEY": "ambient_cartesia", "HERMES_SECRETS_REFRESH": "1",
            "HERMES_PERSONA_APPEND_FILE": str(self.ambient / "persona.md"),
            "HERMES_AGENT_LLM_PROVIDER": "ambient", "HERMES_AGENT_LLM_MODEL": "ambient",
            "HERMES_AGENT_LLM_THINKING": "low", "HERMES_AGENT_TERMINAL_BACKEND": "docker",
            "AGENTIC_HOST_CLASS": "ambient", "AGENTIC_COSW_PLANE": "ambient",
            "USER": "ambient-user", "LOGNAME": "ambient-user",
        })
        ambient_patch = patch.dict(os.environ, poisoned, clear=False)
        ambient_patch.start()
        self.addCleanup(ambient_patch.stop)
        fixture_patch = patch.dict(os.environ, {
            "HOME": str(self.fake_home),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "PI_AGENT_DIR": str(self.pi_agent),
            "HERMES_AGENT_PROFILE_PATH": str(self.fixture_profiles),
            "HERMES_PROJECT_REGISTRY_PATH": str(self.root / "registry"),
            "HERMES_PROJECT_REGISTRY_DIRS": str(self.root / "registry"),
            "AGENTIC_HOST_CLASS": "work", "AGENTIC_COSW_PLANE": "fixture",
            "USER": "", "LOGNAME": "",
        }, clear=True)
        fixture_patch.start()
        self.addCleanup(fixture_patch.stop)

        # Exercise real skill-link creation, but never link back to the checkout.
        self.script_dir = self.root / "tooling" / "bin" / "hermes"
        self.script_dir.mkdir(parents=True)
        for family in ("pi", "shared"):
            skill = self.root / "tooling" / "skills" / family / "fixture-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("Fixture skill\n")
        main_home = self.fake_home / ".hermes"
        main_home.mkdir()
        (main_home / "auth.json").write_text('{}\n')

    def load_module(self):
        # Both exports above must make _apply_host_env return without probing.
        with patch("subprocess.check_output", side_effect=AssertionError("host probe forbidden")):
            module = load_module()
        self.assertEqual(module.MAIN_HOME, self.fake_home / ".hermes")
        self.assertEqual(module._SECRETS_DIR, self.fake_home / ".local/share/hermes-secrets")
        self.assertEqual(module._CURSOR_META, module._SECRETS_DIR / "cursor.meta.json")
        self.assertEqual(module._DEFAULT_PROFILE_DIRS, [
            self.fake_home / "src/karan.hiremath/agentic/hermes/profiles",
            self.fake_home / "src/hermes/profiles",
            MODULE_PATH.parent / "profiles",
        ])
        for attr, value in (
            ("SCRIPT_DIR", self.script_dir),
            ("PLUGIN_DIR", self.script_dir / "plugins/cartesia"),
            ("TEMPLATE_PATH", self.script_dir / "profiles/TEMPLATE.yaml"),
        ):
            replacement = patch.object(module, attr, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        # Only external lookup boundaries are mocked; env, dotenv, cache and
        # fixture Pi auth resolution, staging and materialization remain real.
        for attr, kwargs in (
            ("_keychain_get_cursor_key", {"return_value": None}),
            ("_keychain_set_cursor_key", {"side_effect": AssertionError("keychain write forbidden")}),
            ("_cursor_api_key_from_op", {"side_effect": AssertionError("1Password lookup forbidden")}),
        ):
            boundary = patch.object(module, attr, **kwargs)
            boundary.start()
            self.addCleanup(boundary.stop)
        return module

    def materialize(self, module):
        self.assertEqual(module.profile_path(), [Path(os.environ["HERMES_AGENT_PROFILE_PATH"])])
        self.assertFalse(module._secrets_refresh_requested())
        self.assertIsNone(module._shared_people_root())
        for path in (module._data_home(), Path(os.environ["PI_AGENT_DIR"]),
                     Path(os.environ["XDG_CONFIG_HOME"]), Path(os.environ["XDG_CACHE_HOME"])):
            self.assertTrue(path.resolve().is_relative_to(self.root.resolve()), path)
        home = module.materialize("chief-of-staff-work")
        self.assertEqual(home, Path(os.environ["XDG_DATA_HOME"]) / "hermes-agents/chief-of-staff-work")
        runtime = home / "profiles/chief-of-staff-work"
        for destination in (home, runtime, module.MAIN_HOME, module._SECRETS_DIR):
            self.assertTrue(destination.resolve().is_relative_to(self.root.resolve()), destination)
        for path in home.rglob("*"):
            if path.is_symlink():
                self.assertTrue(path.resolve().is_relative_to(self.root.resolve()), path)
            elif path.is_file():
                self.assertNotIn(b"ambient_", path.read_bytes(), path)
                self.assertNotIn(b"ambient persona", path.read_bytes(), path)
        for destination in (home, runtime):
            self.assertEqual((destination / "auth.json").resolve(), (module.MAIN_HOME / "auth.json").resolve())
            self.assertTrue((destination / "skills/fixture-skill").is_symlink())
        self.assertEqual({
            path.relative_to(self.ambient): path.read_bytes()
            for path in self.ambient.rglob("*") if path.is_file()
        }, self.ambient_snapshot)
        return home


class HermesAgentsLlmRenderTest(ContainedHermesTest):
    def test_render_passes_cursor_model_and_thinking_to_hermes_config(self):
        module = self.load_module()
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
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
                module = self.load_module()
                home = self.materialize(module)
            config = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(config["model"]["provider"], "cursor")
            self.assertEqual(config["model"]["default"], "grok-4.6:fast")
            self.assertEqual(config["agent"]["reasoning_effort"], "xhigh")
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("CURSOR_API_KEY"), "cursor_test_key")
            runtime_env = module._read_env_file(home / "profiles/chief-of-staff-work/.env")
            self.assertEqual(runtime_env.get("CURSOR_API_KEY"), "cursor_test_key")
            self.assertFalse((module.MAIN_HOME / ".env").exists())
            self.assertFalse((self.fake_home / ".cursor/agent.env").exists())

    def test_materialize_syncs_together_key_from_pi_auth(self):
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
                module = self.load_module()
                self.assertNotIn("TOGETHER_API_KEY", os.environ)
                home = self.materialize(module)
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("TOGETHER_API_KEY"), "pi_together_test_key")
            runtime_env = module._read_env_file(home / "profiles/chief-of-staff-work/.env")
            self.assertEqual(runtime_env.get("TOGETHER_API_KEY"), "pi_together_test_key")
            self.assertNotIn("CURSOR_API_KEY", env_file)
            module._keychain_get_cursor_key.assert_called_once_with()
            module._cursor_api_key_from_op.assert_not_called()

    def test_materialize_syncs_cursor_key_from_pi_auth(self):
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
                module = self.load_module()
                self.assertNotIn("CURSOR_API_KEY", os.environ)
                home = self.materialize(module)
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("CURSOR_API_KEY"), "pi_cursor_test_key")
            for destination in (
                module.MAIN_HOME / ".env",
                self.fake_home / ".cursor/agent.env",
                home / "profiles/chief-of-staff-work/.env",
            ):
                self.assertTrue(destination.resolve().is_relative_to(self.root.resolve()))
                self.assertEqual(module._read_env_file(destination).get("CURSOR_API_KEY"), "pi_cursor_test_key")
            self.assertEqual(module._file_cache_path().read_text().strip(), "pi_cursor_test_key")
            self.assertTrue(module._CURSOR_META.is_file())
            module._keychain_get_cursor_key.assert_not_called()
            module._cursor_api_key_from_op.assert_not_called()

    def test_llm_env_overrides_and_local_backend_clears_docker_env(self):
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
                module = self.load_module()
                home = self.materialize(module)
            config = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(config["model"]["provider"], "openai-codex")
            self.assertEqual(config["model"]["default"], "gpt-5.5")
            self.assertEqual(config["terminal"]["backend"], "local")
            self.assertEqual(config["terminal"]["cwd"], str(root / "work"))
            self.assertNotIn("docker_image", config["terminal"])
            env_file = module._read_env_file(home / ".env")
            self.assertEqual(env_file.get("TERMINAL_ENV"), "local")
            self.assertEqual(env_file.get("CURSOR_API_KEY"), "keep")
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


class HermesAgentsModelRouterTest(ContainedHermesTest):
    ROUTER_LLM = {"provider": "cursor", "model": "grok-4.6:fast", "thinking": "xhigh"}
    ROUTER_CHAIN = [
        {"provider": "openai-codex", "model": "gpt-5.5"},
        {"provider": "openai-codex", "model": "gpt-5.6-luna"},
        {"provider": "openai-codex", "model": "gpt-5.6-terra"},
        {"provider": "openai-codex", "model": "gpt-5.6-sol"},
        {"provider": "cursor", "model": "grok-4.6:fast"},
    ]

    def test_router_fills_missing_llm_keys_and_installs_chain_excluding_primary(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
        module = self.load_module()
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
        module = self.load_module()
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
        module = self.load_module()
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            _write_seat(profiles, llm={"provider": "cursor", "model": "grok-4.6:fast"})
            with patch.dict(os.environ, {"HERMES_AGENT_PROFILE_PATH": str(profiles)}, clear=False):
                profile = module.load_profile("chief-of-staff-work")
            self.assertNotIn("fallback_model", profile)
            self.assertEqual(profile["llm"]["provider"], "cursor")

    def test_render_config_passes_fallback_chain_and_fails_closed(self):
        module = self.load_module()
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
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
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
                module = self.load_module()
                home = self.materialize(module)
            config = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(config["model"]["default"], "gpt-5.5")
            chain = config["fallback_model"]
            self.assertEqual(chain[0], {"provider": "openai-codex", "model": "gpt-5.6-luna"})
            self.assertNotIn({"provider": "openai-codex", "model": "gpt-5.5"}, chain)


if __name__ == "__main__":
    unittest.main()
