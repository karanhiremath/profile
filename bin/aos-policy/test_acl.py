#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from acl import add_jit_grant, allowed, require  # noqa: E402
from schema import load_bundle  # noqa: E402


def bundle(home: Path | None = None):
    return load_bundle(ROOT / "config" / "aos" / "policy", home or Path(tempfile.mkdtemp()))


class AclTests(unittest.TestCase):
    def test_implementor_reads_not_writes(self):
        b = bundle()
        actor = {"agent": "worker", "class": "implementor"}
        self.assertTrue(allowed(b, actor, "policy.read"))
        self.assertFalse(allowed(b, actor, "policy.write"))
        with self.assertRaises(PermissionError):
            require(b, actor, "policy.write", "herm-tui-cursor-exclusive")

    def test_orchestrator_writes(self):
        b = bundle()
        actor = {"agent": "cosw", "class": "orchestrator"}
        self.assertTrue(allowed(b, actor, "policy.write", "herm-tui-cursor-exclusive"))
        self.assertTrue(allowed(b, actor, "policy.grant"))

    def test_jit_grant(self):
        home = Path(tempfile.mkdtemp())
        b = bundle(home)
        grant = add_jit_grant(
            actor={"agent": "cosw", "class": "orchestrator"},
            bundle=b,
            agent="worker",
            capability="policy.write",
            policies=["herm-tui-cursor-exclusive"],
            ttl="2h",
            home=home,
        )
        self.assertTrue(grant["expires"])
        reloaded = bundle(home)
        self.assertTrue(
            allowed(
                reloaded,
                {"agent": "worker", "class": "implementor"},
                "policy.write",
                "herm-tui-cursor-exclusive",
            )
        )


if __name__ == "__main__":
    unittest.main()
