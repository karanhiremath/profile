#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from podman_mounts import live_mount_script, repair, virtiofs_tag


class PodmanMountsTest(unittest.TestCase):
    def test_tag_is_sha256_prefix(self):
        self.assertEqual(virtiofs_tag("/Users"), "a2a0ee2c717462feb1de2f5afd59de5fd2d8")

    def test_repair_writes_default_shares(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "machine.json"
            ign = Path(tmp) / "machine.ign"
            cfg.write_text(json.dumps({"Mounts": []}))
            ign.write_text(
                json.dumps(
                    {
                        "systemd": {
                            "units": [
                                {"name": "ready.service", "enabled": True},
                                {"name": "Volumes-harmony.mount", "enabled": True},
                            ]
                        }
                    }
                )
            )
            rows = repair(cfg, ign)
            self.assertEqual(len(rows), 3)
            mounts = json.loads(cfg.read_text())["Mounts"]
            self.assertEqual([m["Source"] for m in mounts], ["/Users", "/private", "/var/folders"])
            names = [u["name"] for u in json.loads(ign.read_text())["systemd"]["units"]]
            self.assertIn("ready.service", names)
            self.assertIn("Users.mount", names)
            self.assertNotIn("Volumes-harmony.mount", names)

    def test_live_script_uses_hashed_tags(self):
        script = live_mount_script()
        self.assertIn(virtiofs_tag("/Users"), script)
        self.assertIn("mount -t virtiofs", script)


if __name__ == "__main__":
    unittest.main()
