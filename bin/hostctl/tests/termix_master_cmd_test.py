#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from termix_master_cmd import parse_command


class TermixMasterCmdTest(unittest.TestCase):
    def test_empty_is_help(self):
        self.assertEqual(parse_command(""), "help")
        self.assertEqual(parse_command("hostctl"), "help")

    def test_allowlist(self):
        self.assertEqual(parse_command("status"), ["status"])
        self.assertEqual(parse_command("hostctl omarchy ports"), ["omarchy", "ports"])
        self.assertEqual(parse_command("hostctl omarchy bind"), ["omarchy", "bind"])
        self.assertEqual(parse_command("termix serve"), ["termix", "serve"])

    def test_unwraps_termix_exec(self):
        wrapped = "(\nstatus\n)\nprintf '\\n__TERMIX_EXIT=%d\\n' \"$?\"\n"
        self.assertEqual(parse_command(wrapped), ["status"])
        wrapped_hostctl = "(\nhostctl omarchy ports\n)\nprintf '\\n__TERMIX_EXIT=%d\\n' \"$?\"\n"
        self.assertEqual(parse_command(wrapped_hostctl), ["omarchy", "ports"])

    def test_refuses_shell(self):
        with self.assertRaises(ValueError):
            parse_command("bash")
        with self.assertRaises(ValueError):
            parse_command("status; rm -rf /")
        with self.assertRaises(ValueError):
            parse_command("omarchy install")
        with self.assertRaises(ValueError):
            parse_command("termix status --evil")


if __name__ == "__main__":
    unittest.main()
