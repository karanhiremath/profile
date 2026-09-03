#!/usr/bin/env python3
"""Launch-scoped LLM seat overrides for Cos / agents materialize."""
from __future__ import annotations

import os
import unittest

import hermes_agents as ha


class LlmOverrideTests(unittest.TestCase):
    def test_yaml_default(self) -> None:
        llm = ha.llm_from_profile({"llm": {"provider": "cursor", "model": "grok-4.6:fast"}})
        self.assertEqual(llm["provider"], "cursor")
        self.assertEqual(llm["model"], "grok-4.6:fast")

    def test_env_override(self) -> None:
        os.environ["HERMES_AGENT_LLM_PROVIDER"] = "openai-codex"
        os.environ["HERMES_AGENT_LLM_MODEL"] = "gpt-5.5"
        try:
            llm = ha.llm_from_profile({"llm": {"provider": "cursor", "model": "grok-4.6:fast"}})
            self.assertEqual(llm["provider"], "openai-codex")
            self.assertEqual(llm["model"], "gpt-5.5")
        finally:
            os.environ.pop("HERMES_AGENT_LLM_PROVIDER", None)
            os.environ.pop("HERMES_AGENT_LLM_MODEL", None)


if __name__ == "__main__":
    unittest.main()
