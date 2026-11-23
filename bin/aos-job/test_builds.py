import json
from pathlib import Path
import subprocess
import tempfile
import unittest

AOS = Path(__file__).resolve().parents[1] / "aos"


class BuildTest(unittest.TestCase):
    def test_exact_id_and_duplicate_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            journal = root / "watch.jsonl"
            events = [dict(event="terminal", label="lane", uuid="old", status="SUCCESS", digest="sha256:fixture"),
                      dict(event="status", label="lane", uuid="new", status="WORKING"),
                      dict(event="terminal", label="failed", uuid="failed", status="FAILURE")]
            journal.write_text("".join(json.dumps(e) + "\n" for e in events) + '{"partial":')
            board = subprocess.check_output([AOS, "builds", "--journal", journal, "--case", "fixture"], timeout=5)
            rows = {row["buildId"]: row for row in json.loads(board)}
            self.assertEqual(rows["new"]["status"], "WORKING")
            self.assertEqual(rows["old"]["digest"], "sha256:fixture")
            base = [AOS, "chain", "--journal", journal, "--claims", root / "claims", "--timeout", "1"]

            def launch(label, build):
                return subprocess.run(base + ["--label", label, "--build-id", build, "--", "/bin/echo", "ran"],
                                      capture_output=True, timeout=6)

            self.assertEqual(launch("lane", "new").returncode, 124)
            self.assertEqual(launch("failed", "failed").returncode, 4)
            self.assertEqual(launch("lane", "old").stdout, b"ran\n")
            duplicate = launch("lane", "old")
            self.assertEqual(duplicate.returncode, 3)
            self.assertEqual(duplicate.stdout, b"")


if __name__ == "__main__":
    unittest.main()
