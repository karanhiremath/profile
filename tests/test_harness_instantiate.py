from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_INSTANTIATE = ROOT / "bin/hermes/harness-instantiate"


def classify(profile_text: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "seat.yaml").write_text(profile_text, encoding="utf-8")
        env = os.environ.copy()
        env["HERMES_AGENT_PROFILE_PATH"] = tmp
        proc = subprocess.run(
            [str(HARNESS_INSTANTIATE), "classify", "seat"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    lines = proc.stdout.splitlines()
    assert len(lines) == 1, proc.stdout
    return json.loads(lines[0])


class HarnessInstantiateTest(unittest.TestCase):
    def test_typed_plane_and_lane_win_over_path(self):
        payload = classify("name: seat\nplane: work\nlane: ops\n")
        self.assertEqual(payload["schema"], "harness-instantiate.v1")
        self.assertEqual(payload["plane"], "work")
        self.assertEqual(payload["lane"], "ops")
        self.assertEqual(payload["reason"], "plane-from-profile")

    def test_path_inference_is_fallback_reason(self):
        payload = classify("name: seat\n")
        self.assertEqual(payload["plane"], "personal")
        self.assertNotIn("lane", payload)
        self.assertEqual(payload["reason"], "plane-inferred-from-path")


if __name__ == "__main__":
    unittest.main()
