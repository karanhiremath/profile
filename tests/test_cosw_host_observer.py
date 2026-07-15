from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin/hermes/cosw-host-observer"


class HostObserverFreshStateTest(unittest.TestCase):
    def test_initial_snapshot_survives_head_pipe_close_with_many_session_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            sessions = home / ".pi/agent/sessions"
            state = Path(tmp) / "observer"
            sessions.mkdir(parents=True)
            # emit_recent_files limits this source to 400 rows. More inputs
            # force head to close the pipeline early, the original fresh-state
            # bootstrap failure under `set -o pipefail`.
            for index in range(405):
                (sessions / f"session-{index:03d}.json").write_text("{}\n")
            env = {**os.environ, "HOME": str(home)}
            subprocess.run(
                [str(SCRIPT), "once", "--state-dir", str(state)],
                env=env,
                text=True,
                capture_output=True,
                check=True,
                timeout=30,
            )
            self.assertTrue((state / "current/SUMMARY.md").is_file())
            index = (state / "current/live-jsonl-index.tsv").read_text()
            self.assertIn("pi-agent", index)


if __name__ == "__main__":
    unittest.main()
