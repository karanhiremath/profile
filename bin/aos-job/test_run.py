import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

AOS = Path(__file__).resolve().parents[1] / "aos"


class JobRunTest(unittest.TestCase):
    def test_heartbeat_and_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            command = [AOS, "job", "run", "--target-sid", "coordinator", "--summary", root / "result.md",
                       "--heartbeat", "1", "--", "/bin/sh", "-c", 'printf "%s" "$1"; sleep 2; exit 7',
                       "fixture", "private argument"]
            result = subprocess.run(command, env=dict(os.environ, PI_AGENT=folder), capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 7)
            self.assertEqual(result.stdout, b"private argument")
            status, = (root / "jobs/sessions/coordinator").glob("*.status.json")
            row = json.loads(status.read_text())
            self.assertEqual((row["targetSid"], row["status"], row["exitCode"]), ("coordinator", "failed", 7))
            self.assertEqual(row["summaryPath"], str(root / "result.md"))
            journal = Path(row["eventsPath"]).read_text()
            self.assertNotIn("private argument", journal)
            kinds = [json.loads(line)["type"] for line in journal.splitlines()]
            self.assertEqual(kinds[0], "job.started")
            self.assertIn("job.heartbeat", kinds)
            self.assertEqual(kinds[-1], "job.failed")

    def test_target_validation_and_launch_error(self):
        with tempfile.TemporaryDirectory() as folder:
            base = [AOS, "job", "run", "--inbox", folder, "--summary", "/result"]
            result = subprocess.run(base + ["--target-sid", "..", "--", "/bin/true"], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(list(Path(folder).iterdir()))
            result = subprocess.run(base + ["--target-sid", "coord", "--", "/no-such-command"], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 127)
            row = json.loads(next(Path(folder).glob("*.status.json")).read_text())
            self.assertEqual((row["status"], row["exitCode"]), ("failed", 127))


if __name__ == "__main__":
    unittest.main()
