from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AOS = ROOT / "bin/aos"


class AosStatusJsonTest(unittest.TestCase):
    def test_status_json_stdout_is_one_object_and_human_text_is_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            pi_agent = root / "pi-agent"
            harness_dir = profile / "bin" / "atop"
            harness_dir.mkdir(parents=True)
            pi_agent.mkdir()
            harness = harness_dir / "harness-sync"
            harness.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [ \"${1:-}\" = status ]; then\n"
                "  printf 'human harness status on stdout\\n'\n"
                "  printf 'human harness status on stderr\\n' >&2\n"
                "  exit 0\n"
                "fi\n"
                "exit 2\n",
                encoding="utf-8",
            )
            harness.chmod(harness.stat().st_mode | stat.S_IXUSR)
            (pi_agent / "extensions").mkdir()
            (pi_agent / "job-bus.json").write_text("{}\n", encoding="utf-8")
            (pi_agent / "extensions" / "job-bus.ts").write_text("// test\n", encoding="utf-8")
            env = os.environ.copy()
            env["PROFILE_DIR"] = str(profile)
            env["PI_AGENT"] = str(pi_agent)
            proc = subprocess.run(
                [str(AOS), "status", "--json"],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        payload = json.loads(lines[0])
        self.assertEqual(payload["schema"], "aos-status.v1")
        self.assertEqual(payload["profile"], str(profile))
        self.assertTrue(payload["harness_sync"]["present"])
        self.assertEqual(payload["harness_sync"]["status_rc"], 0)
        self.assertTrue(payload["job_bus"]["configured"])
        self.assertTrue(payload["job_bus"]["extension_present"])
        self.assertIn("human harness status on stdout", proc.stderr)
        self.assertIn("human harness status on stderr", proc.stderr)


if __name__ == "__main__":
    unittest.main()
