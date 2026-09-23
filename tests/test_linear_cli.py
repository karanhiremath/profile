from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin/linear-cli/linear"


def load_mod():
    loader = importlib.machinery.SourceFileLoader("linear_cli", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class LinearCliTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_mod()

    def test_parse_priority(self):
        self.assertEqual(self.mod.parse_priority("high"), 2)
        self.assertEqual(self.mod.parse_priority("1"), 1)
        with self.assertRaises(self.mod.LinearError):
            self.mod.parse_priority("critical")

    def test_load_api_key_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "linear-token"
            path.write_text("lin_api_testkey\n", encoding="utf-8")
            env = {"LINEAR_API_KEY_FILE": str(path)}
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("LINEAR_API_KEY", None)
                self.assertEqual(self.mod.load_api_key(), "lin_api_testkey")

    def test_load_api_key_prefers_env(self):
        with mock.patch.dict(os.environ, {"LINEAR_API_KEY": "lin_api_env"}, clear=False):
            self.assertEqual(self.mod.load_api_key(), "lin_api_env")

    def test_flatten_issue(self):
        issue = {
            "identifier": "KH-1",
            "title": "t",
            "url": "https://linear.app/x/issue/KH-1",
            "state": {"name": "Todo"},
            "team": {"key": "KH"},
            "project": {"name": "P"},
            "assignee": {"email": "a@example.com"},
            "priority": 3,
            "dueDate": None,
            "updatedAt": "2026-01-01T00:00:00Z",
            "description": "hello",
            "id": "uuid",
        }
        flat = self.mod.flatten_issue(issue, full=False)
        self.assertEqual(flat["identifier"], "KH-1")
        self.assertNotIn("description", flat)

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as cm:
            self.mod.build_parser().parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_whoami_dry_run_does_not_need_network_shape(self):
        parser = self.mod.build_parser()
        args = parser.parse_args(["--dry-run", "issue", "get", "KH-1"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.identifier, "KH-1")

    def test_table_after_subcommand(self):
        hoisted = self.mod.hoist_global_flags(["whoami", "--table"])
        args = self.mod.build_parser().parse_args(hoisted)
        self.assertTrue(args.table)
        self.assertEqual(args.command, "whoami")


if __name__ == "__main__":
    unittest.main()
