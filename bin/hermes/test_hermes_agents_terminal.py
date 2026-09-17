#!/usr/bin/env python3
"""Terminal backend resolution for Hermes agent materialize."""
from __future__ import annotations

import os
import unittest
from unittest import mock

import hermes_agents as ha


class TerminalResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "HERMES_AGENT_TERMINAL_BACKEND",
                "TERMINAL_ENV",
                "TERMINAL_DOCKER_VOLUMES",
                "TERMINAL_DOCKER_IMAGE",
                "TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES",
                "TERMINAL_CWD",
            )
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_host_tools_override_beats_profile_docker(self) -> None:
        os.environ["TERMINAL_ENV"] = "local"
        term = ha.resolve_terminal({"terminal": {"backend": "docker"}})
        self.assertEqual(term, {"backend": "local"})
        self.assertEqual(ha.terminal_env_updates(term)["TERMINAL_ENV"], "local")

    def test_terminal_env_docker_applies_volumes(self) -> None:
        os.environ["TERMINAL_ENV"] = "docker"
        os.environ["TERMINAL_DOCKER_VOLUMES"] = '["/tmp/src:/root/src"]'
        term = ha.resolve_terminal({})
        self.assertEqual(term["backend"], "docker")
        self.assertEqual(term["docker_volumes"], ["/tmp/src:/root/src"])

    def test_profile_docker_gets_env_volumes_without_override(self) -> None:
        os.environ["TERMINAL_DOCKER_VOLUMES"] = '["/tmp/src:/root/src"]'
        term = ha.resolve_terminal({"terminal": {"backend": "docker"}})
        self.assertEqual(term["backend"], "docker")
        self.assertEqual(term["docker_volumes"], ["/tmp/src:/root/src"])
        updates = ha.terminal_env_updates(term)
        self.assertEqual(updates["TERMINAL_ENV"], "docker")


class CursorKeySourceTests(unittest.TestCase):
    def test_default_op_ref_is_employee_on_cartesia_account(self) -> None:
        saved = {
            key: os.environ.get(key)
            for key in (
                "HERMES_CURSOR_OP_ACCOUNT",
                "HERMES_CURSOR_OP_REF",
                "HERMES_CURSOR_OP_FALLBACK_REF",
            )
        }
        for key in saved:
            os.environ.pop(key, None)
        try:
            account, ref = ha.cursor_op_candidates()[0]
            self.assertEqual(account, "cartesia.1password.com")
            self.assertEqual(ref, "op://Employee/Cursor pi-coding-agent/credential")
            secrets = ha.cursor_onepassword_secrets()
            self.assertFalse(secrets["onepassword"]["enabled"])
            cfg = ha._render_config({"llm": {"provider": "openai-codex"}, "tts": {"enabled": False}, "stt": {"enabled": False}})
            self.assertFalse(cfg["secrets"]["onepassword"]["enabled"])
            self.assertNotIn("env", cfg["secrets"]["onepassword"])
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_resolve_skips_op_when_file_cache_present(self) -> None:
        calls = {"op": 0}

        def boom() -> None:
            calls["op"] += 1
            raise AssertionError("op must not run on cache hit")

        saved = os.environ.get("CURSOR_API_KEY")
        os.environ.pop("CURSOR_API_KEY", None)
        os.environ.pop("HERMES_SECRETS_REFRESH", None)
        try:
            with mock.patch.object(ha, "_file_cache_get", return_value="cached-key"):
                with mock.patch.object(ha, "_cursor_api_key_from_op", side_effect=boom):
                    self.assertEqual(ha._resolve_cursor_api_key(), "cached-key")
            self.assertEqual(calls["op"], 0)
        finally:
            if saved is None:
                os.environ.pop("CURSOR_API_KEY", None)
            else:
                os.environ["CURSOR_API_KEY"] = saved


class CursorSeatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in ("HERMES_AGENT_LLM_PROVIDER", "HERMES_AGENT_LLM_MODEL")
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_keeps_grok_fast_suffix(self) -> None:
        self.assertEqual(ha._cursor_sdk_model("grok-4.6:fast"), "grok-4.6:fast")
        self.assertEqual(ha._cursor_sdk_model("grok-4.6"), "grok-4.6")

    def test_render_keeps_fast_seat_and_steer(self) -> None:
        cfg = ha._render_config(
            {
                "llm": {"provider": "cursor", "model": "grok-4.6:fast"},
                "display": {"busy_input_mode": "steer"},
                "tts": {"enabled": False},
                "stt": {"enabled": False},
            }
        )
        self.assertEqual(cfg["model"], {"provider": "cursor", "default": "grok-4.6:fast"})
        self.assertEqual(cfg["display"]["busy_input_mode"], "steer")

    def test_render_passes_voice_auto_tts(self) -> None:
        cfg = ha._render_config(
            {
                "llm": {"provider": "cursor", "model": "grok-4.6:fast"},
                "tts": {"enabled": True, "model": "sonic-3.6", "voice": ""},
                "stt": {"enabled": True, "model": "ink-preview", "language": "en"},
                "voice": {"auto_tts": True, "record_key": "ctrl+b"},
            }
        )
        self.assertEqual(cfg["voice"], {"auto_tts": True, "record_key": "ctrl+b"})
        self.assertEqual(cfg["tts"]["provider"], "cartesia")


if __name__ == "__main__":
    unittest.main()
