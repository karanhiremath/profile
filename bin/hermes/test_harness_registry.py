#!/usr/bin/env python3
"""Registry + eval-plan unit tests. No live LLM."""
from __future__ import annotations

import importlib.machinery
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
reg = importlib.machinery.SourceFileLoader(
    "harness_registry", str(Path(__file__).with_name("harness-registry.py"))
).load_module()
ev = importlib.machinery.SourceFileLoader(
    "harness_eval", str(Path(__file__).with_name("harness-eval"))
).load_module()


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = reg.load(ROOT / "config/harness/registry.toml")

    def test_required_harnesses(self) -> None:
        names = set(reg.names(self.data))
        for required in ("pi", "omp", "hermes-agent", "herm", "herdr", "cursor-cli"):
            self.assertIn(required, names)

    def test_policy_seats(self) -> None:
        policy = self.data["policy"]
        self.assertEqual(policy["default_live_seat"], "cursor/grok-4.6:fast")
        self.assertEqual(policy["failure_mode_cot_seat"], "openai-codex/gpt-5.5")
        self.assertFalse(policy["nightly_promotes"])

    def test_host_classes(self) -> None:
        hosts = set(reg.host_classes(self.data))
        self.assertTrue({"work-mbp", "tc2", "work-devbox", "personal-mini", "omarchy"} <= hosts)

    def test_pin_installers_exist(self) -> None:
        for name, spec in reg.pins(self.data).items():
            install = spec.get("install")
            if install:
                self.assertTrue((ROOT / install).exists(), f"{name} {install}")

    def test_host_mise_files_exist(self) -> None:
        for name, spec in self.data["hosts"].items():
            self.assertTrue((ROOT / spec["mise"]).exists(), name)


class EvalPlanTests(unittest.TestCase):
    def test_dry_run_default_seat(self) -> None:
        code = ev.main(["--dry-run"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
