#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from cli_dispatch import classify, reserved_session_names


class CliDispatchTest(unittest.TestCase):
    def test_empty_is_official(self):
        self.assertEqual(classify([]), ("official", []))

    def test_wrapper_and_official_verbs(self):
        self.assertEqual(classify(["status"]), ("wrapper", ["status"]))
        self.assertEqual(classify(["snippets", "list"]), ("official", ["snippets", "list"]))
        self.assertEqual(classify(["hosts", "list"]), ("official", ["hosts", "list"]))
        self.assertEqual(classify(["--json", "hosts", "list"]), ("official", ["--json", "hosts", "list"]))

    def test_passthrough_and_sync(self):
        self.assertEqual(classify(["--", "whoami"]), ("official", ["whoami"]))
        self.assertEqual(classify(["snippets-sync"]), ("snippets-sync", []))
        self.assertEqual(classify(["snippets-sync", "--dry-run"]), ("snippets-sync", ["--dry-run"]))

    def test_session_shorthand(self):
        self.assertEqual(classify(["cos"]), ("attach", ["cos"]))
        self.assertEqual(classify(["termix"]), ("attach", ["termix"]))
        self.assertEqual(classify(["attach", "status"]), ("attach", ["status"]))
        self.assertEqual(classify(["--ls"]), ("attach", ["--ls"]))

    def test_reserved_session_names_include_cli_verbs(self):
        reserved = reserved_session_names()
        self.assertIn("status", reserved)
        self.assertIn("snippets", reserved)
        self.assertIn("attach", reserved)
        self.assertNotIn("cos", reserved)


if __name__ == "__main__":
    unittest.main()
