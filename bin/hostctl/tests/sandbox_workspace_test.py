#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NIXOS = ROOT / "sandboxes" / "nixos"


class SandboxWorkspaceTest(unittest.TestCase):
    def test_nixos_workspace_files(self):
        self.assertTrue((NIXOS / "flake.nix").is_file())
        self.assertTrue((NIXOS / "devbox.json").is_file())
        self.assertTrue((NIXOS / "mise.toml").is_file())
        self.assertNotIn("nodejs", (NIXOS / "devbox.json").read_text())
        self.assertNotIn("node", (NIXOS / "mise.toml").read_text())
        spec = json.loads((NIXOS / "devbox.json").read_text())
        self.assertIn("python@3.13", spec["packages"])
        self.assertIn("rustc@latest", spec["packages"])
        self.assertIn("elixir@latest", spec["packages"])
        self.assertIn("go@latest", spec["packages"])

    def test_node_web_is_separate_opt_in(self):
        spec = json.loads((NIXOS / "node-web.devbox.json").read_text())
        self.assertEqual(spec["env"]["HOSTCTL_BUNDLER"], "vite")
        self.assertTrue(any(item.startswith("pnpm@") for item in spec["packages"]))


if __name__ == "__main__":
    unittest.main()
