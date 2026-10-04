#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from attach_spec import parse_alias, parse_argv, pick_family


INVENTORY = {
    "attach": {
        "defaults": {
            "instance": "default",
            "personal_family": "nixos",
            "session_by_kind": {"mac": "mac", "oma": "home"},
        },
        "kinds": {
            "mac": {"role": "host", "os_class": "macos"},
            "oma": {"role": "peer", "os_class": "omarchy"},
        },
        "instances": {
            "default": {
                "title": "default",
                "oma": {
                    "targets": [
                        "try-omarchy.tail1e8436.ts.net",
                        "try-omarchy",
                    ]
                },
            },
            "lab": {
                "title": "lab",
                "oma": {"targets": ["lab-omarchy.tail1e8436.ts.net"]},
            },
        },
        "sandbox": {
            "default_family": "nixos",
            "pool": ["nixos", "rust", "elixir", "mojo", "go", "python"],
        },
    }
}


class AttachSpecTest(unittest.TestCase):
    def test_parse_alias_plain_and_sandbox(self):
        self.assertEqual(parse_alias("oma", INVENTORY), ("oma", None, False))
        self.assertEqual(parse_alias("oma-s", INVENTORY), ("oma", None, True))
        self.assertEqual(parse_alias("mac-s", INVENTORY), ("mac", None, True))
        self.assertEqual(parse_alias("oma-default", INVENTORY), ("oma", "default", False))
        self.assertEqual(parse_alias("oma-default-s", INVENTORY), ("oma", "default", True))
        self.assertEqual(parse_alias("oma-lab-s", INVENTORY), ("oma", "lab", True))

    def test_sorroma_is_not_an_alias(self):
        with self.assertRaises(ValueError):
            parse_alias("sorroma", INVENTORY)

    def test_oma_defaults_to_home_on_default_instance(self):
        spec = parse_argv(["oma"], INVENTORY)
        self.assertEqual(spec.kind, "oma")
        self.assertEqual(spec.instance, "default")
        self.assertFalse(spec.sandbox)
        self.assertEqual(spec.session, "home")
        self.assertEqual(
            spec.targets,
            ("try-omarchy.tail1e8436.ts.net", "try-omarchy"),
        )

    def test_flag_and_positional_session(self):
        spec = parse_argv(["oma-default", "cos"], INVENTORY)
        self.assertEqual(spec.instance, "default")
        self.assertEqual(spec.session, "cos")
        spec = parse_argv(["oma", "--instance", "lab", "--session", "cos"], INVENTORY)
        self.assertEqual(spec.instance, "lab")
        self.assertEqual(spec.session, "cos")
        self.assertEqual(spec.targets, ("lab-omarchy.tail1e8436.ts.net",))

    def test_sandbox_defaults_to_nixos_not_node_or_ubuntu(self):
        spec = parse_argv(["mac-s", "notes"], INVENTORY)
        self.assertTrue(spec.sandbox)
        self.assertEqual(spec.kind, "mac")
        self.assertEqual(spec.family, "nixos")
        self.assertNotIn("ubuntu", spec.family or "")
        self.assertNotIn("node", spec.family or "")
        self.assertEqual(pick_family("notes", inventory=INVENTORY), "nixos")
        self.assertEqual(pick_family("other-session", inventory=INVENTORY), "nixos")

    def test_family_flag_wins(self):
        spec = parse_argv(["oma-default-s", "--family", "rust"], INVENTORY)
        self.assertEqual(spec.family, "rust")
        self.assertEqual(spec.session, "home")

    def test_node_web_is_opt_in_only(self):
        spec = parse_argv(["mac-s", "--family", "node-web", "ui"], INVENTORY)
        self.assertEqual(spec.family, "node-web")
        self.assertNotIn("node-web", INVENTORY["attach"]["sandbox"]["pool"])

    def test_ls_does_not_take_session(self):
        spec = parse_argv(["oma", "--ls"], INVENTORY)
        self.assertTrue(spec.list_sessions)
        with self.assertRaises(ValueError):
            parse_argv(["oma", "--ls", "home"], INVENTORY)


if __name__ == "__main__":
    unittest.main()
