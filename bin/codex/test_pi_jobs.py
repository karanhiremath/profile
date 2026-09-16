import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("pi_jobs", Path(__file__).with_name("pi-jobs.py"))
jobs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jobs)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.home_patch = patch.object(Path, "home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.payload = {"session_id": "session-one", "hook_event_name": "PostToolUse",
                        "tool_response": "SECRET_TOOL_OUTPUT"}

    def record(self, name="job-one", status="succeeded", session="session-one", **extra):
        root = jobs.session_root(session)
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{name}.status.json"
        jobs.write_record(path, {"schema": jobs.SCHEMA, "jobId": name, "status": status,
                                 "task": "UNTRUSTED_TASK", "message": "SECRET_MESSAGE", **extra})
        return path

    def test_running_is_quiet_then_success_once(self):
        self.record(status="running")
        self.assertIsNone(jobs.completion_hook(self.payload))
        self.record()
        first = jobs.completion_hook(self.payload)
        self.assertIn("succeeded", json.dumps(first))
        self.assertIsNone(jobs.completion_hook(self.payload))
        for secret in ("SECRET_TOOL_OUTPUT", "UNTRUSTED_TASK", "SECRET_MESSAGE"):
            self.assertNotIn(secret, json.dumps(first))

    def test_failure_and_session_isolation(self):
        self.record(status="failed")
        self.record(name="job-other", session="session-two")
        self.record(name="job-mistargeted", targetSid="session-two")
        output = json.dumps(jobs.completion_hook(self.payload))
        self.assertIn("failed", output)
        self.assertNotIn("job-other", output)
        self.assertNotIn("job-mistargeted", output)

    def test_concurrent_delivery_once(self):
        self.record()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(jobs.completion_hook, [self.payload] * 12))
        self.assertEqual(sum(value is not None for value in results), 1)

    def test_bounded_batches_leave_remaining_jobs_pending(self):
        for index in range(5):
            self.record(name=f"job-{index}")
        first = json.dumps(jobs.completion_hook(self.payload))
        second = json.dumps(jobs.completion_hook(self.payload))
        self.assertEqual(first.count("job_id"), 3)
        self.assertEqual(second.count("job_id"), 2)
        self.assertIsNone(jobs.completion_hook(self.payload))

    def test_invalid_and_symlink_records_are_ignored(self):
        path = self.record()
        path.write_text("{")
        self.assertIsNone(jobs.completion_hook(self.payload))
        path.unlink()
        outside = self.home / "private.json"
        outside.write_text('{"secret":"never read"}')
        path.symlink_to(outside)
        self.assertIsNone(jobs.completion_hook(self.payload))

    def test_invalid_session_and_other_event(self):
        with self.assertRaises(ValueError):
            jobs.session_root("../../elsewhere")
        self.assertIsNone(jobs.completion_hook({**self.payload, "hook_event_name": "PreToolUse"}))

    def test_detached_cli_success_and_failure_keep_approved_arguments(self):
        fake_bin = self.home / "bin"
        fake_bin.mkdir()
        fake = fake_bin / "pi"
        fake.write_text(
            f"#!{sys.executable}\nimport json, sys\n"
            "assert '--cursor-no-local-resume' not in sys.argv\n"
            "assert '--no-tools' in sys.argv\n"
            "print(json.dumps({'arguments':sys.argv[1:]}))\n"
            "sys.exit(7 if 'fixture-failure' in sys.argv else 0)\n"
        )
        fake.chmod(0o700)
        with patch.dict(os.environ, {"PATH": str(fake_bin) + os.pathsep + os.environ['PATH']}):
            for fixture, status in (("fixture-success", "succeeded"), ("fixture-failure", "failed")):
                started = jobs.launch("session-one", self.home, ["--no-tools", fixture])
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    record = jobs.read_record(Path(started["status_path"]))
                    if record.get("status") != "running":
                        break
                    time.sleep(0.02)
                self.assertEqual(record.get("status"), status)
                result = json.loads(Path(started["result_path"]).read_text())
                self.assertEqual(result["arguments"],
                                 ["--mode", "json", "-p", "--no-session", "--no-tools", fixture])
                self.assertIn(status, json.dumps(jobs.completion_hook(self.payload)))
                self.assertIsNone(jobs.completion_hook(self.payload))


if __name__ == "__main__":
    unittest.main()
