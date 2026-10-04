#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LIB))

import lib as cmdk  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_schema_and_ids(self) -> None:
        catalog = cmdk.load_catalog()
        self.assertEqual(catalog["schema"], "profile.cmdk.v1")
        ids = [action["id"] for action in catalog["actions"]]
        for required in ("inject-prompt", "otel-view", "attach-mac", "pc-pick"):
            self.assertIn(required, ids)

    def test_profile_classes(self) -> None:
        classes = cmdk.load_profile_classes()
        self.assertIn("implementor", classes)
        self.assertIn("librarian", classes)
        self.assertTrue(any(item.startswith("agent:cos") for item in classes))


class LayerTests(unittest.TestCase):
    def test_detect(self) -> None:
        cases = [
            ("nvim", "", "pi_profile", "profile", "nvim"),
            ("pi", "π", "ao2", "pi", "harness"),
            ("claude", "", "ao0", "do", "harness"),
            ("btop", "", "pi_profile", "profile-db", "otel"),
            ("zsh", "", "mac", "zsh", "zsh"),
            ("k9s", "metrics", "mac", "db", "otel"),
        ]
        for cmd, title, session, window, expected in cases:
            self.assertEqual(
                cmdk.detect_layer(cmd, title, session, window),
                expected,
                msg=(cmd, title, session, window),
            )


class InjectPolicyTests(unittest.TestCase):
    def test_blocked_cos(self) -> None:
        for target in ("cos", "cos-ao2", "atop", "atop-foo", "notes", "pm"):
            self.assertTrue(cmdk.inject_blocked(target), target)
            self.assertFalse(cmdk.send_keys_allowed(target), target)

    def test_workers_allowed(self) -> None:
        self.assertTrue(cmdk.send_keys_allowed("ao2"))
        self.assertTrue(cmdk.send_keys_allowed("infra0:do.0"))
        self.assertFalse(cmdk.inject_blocked("ao2"))

    def test_pc_harness_allowed(self) -> None:
        self.assertTrue(cmdk.send_keys_allowed("pi_profile", "pi"))
        self.assertFalse(cmdk.send_keys_allowed("mac", "zsh"))

    def test_empty_inject(self) -> None:
        result = cmdk.inject("")
        self.assertFalse(result["ok"])


class RunActionTests(unittest.TestCase):
    def test_class_export(self) -> None:
        result = cmdk.run_action("class:implementor")
        self.assertTrue(result["ok"])
        self.assertEqual(result["export"]["PI_PROFILE_CLASS"], "implementor")

    def test_unknown(self) -> None:
        result = cmdk.run_action("does-not-exist")
        self.assertFalse(result["ok"])

    def test_reload_is_note(self) -> None:
        result = cmdk.run_action("reload-zsh")
        self.assertTrue(result["ok"])
        self.assertIn("reload", result.get("note", ""))


if __name__ == "__main__":
    unittest.main()
