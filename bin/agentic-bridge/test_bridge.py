"""Contract, concurrent writer and damaged-tail checks; no external services."""

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid

SCRIPT = Path(__file__).with_name("main.py")
SPEC = importlib.util.spec_from_file_location("agentic_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bus = Path(self.temp.name) / "runtime" / "events.jsonl"

    def event(self, **changes):
        event = {
            "schema_version": bridge.SCHEMA,
            "event_id": str(uuid.uuid4()),
            "timestamp": "2026-09-13T01:00:00Z",
            "project": "home-infra",
            "privacy": "personal",
            "sender": "codex",
            "recipient": "pi-home-infra",
            "kind": "assignment.created",
            "in_reply_to": None,
            "body": "Line one\nLine two — preserved",
        }
        return event | changes

    def read(self):
        return bridge.read_bus(self.bus, "home-infra", "personal")

    def test_post_is_not_acknowledgment_and_data_is_preserved(self):
        posted = self.event()
        result = bridge.append_event(self.bus, posted)
        self.assertEqual(result["status"], "posted")
        events, partial = self.read()
        self.assertEqual(events, [posted])
        self.assertEqual(bridge.summarize(events, partial)["acknowledged"], 0)
        ack = self.event(kind="ack", in_reply_to=posted["event_id"], sender="pi-home-infra", recipient="codex")
        bridge.append_event(self.bus, ack)
        status = bridge.summarize(*self.read())
        self.assertEqual(status["acknowledged"], 1)
        self.assertEqual(status["unacknowledged_event_ids"], [])
        self.assertEqual(stat.S_IMODE(self.bus.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.bus.parent.stat().st_mode), 0o700)

    def test_concurrent_writers_produce_complete_unique_events(self):
        base = [sys.executable, str(SCRIPT), "append", "--bus", str(self.bus),
                "--project", "home-infra", "--privacy", "personal", "--sender", "codex",
                "--recipient", "pi-home-infra", "--kind", "status"]
        processes = [subprocess.Popen(base + ["--message", f"worker {i}"], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for i in range(16)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "posted")
        events, partial = self.read()
        self.assertFalse(partial)
        self.assertEqual(len(events), 16)
        self.assertEqual(len({event["event_id"] for event in events}), 16)
        self.assertEqual({event["body"] for event in events}, {f"worker {i}" for i in range(16)})

    def test_partial_tail_is_readable_but_cannot_be_appended(self):
        first = self.event()
        bridge.append_event(self.bus, first)
        with self.bus.open("ab") as stream:
            stream.write(b'{"incomplete":')
        before = self.bus.read_bytes()
        events, partial = self.read()
        self.assertEqual(events, [first])
        self.assertTrue(partial)
        with self.assertRaisesRegex(bridge.BridgeError, "unterminated"):
            bridge.append_event(self.bus, self.event())
        self.assertEqual(self.bus.read_bytes(), before)

    def test_missing_newline_is_not_silently_repaired(self):
        bridge.append_event(self.bus, self.event())
        self.bus.write_bytes(self.bus.read_bytes().removesuffix(b"\n"))
        self.assertEqual(self.read(), ([], True))
        with self.assertRaisesRegex(bridge.BridgeError, "unterminated"):
            bridge.append_event(self.bus, self.event())

    def test_malformed_complete_record_refuses_read_and_append(self):
        bridge.append_event(self.bus, self.event())
        with self.bus.open("ab") as stream:
            stream.write(b"not-json\n")
        before = self.bus.read_bytes()
        with self.assertRaisesRegex(bridge.BridgeError, "line 2"):
            self.read()
        with self.assertRaisesRegex(bridge.BridgeError, "line 2"):
            bridge.append_event(self.bus, self.event())
        self.assertEqual(self.bus.read_bytes(), before)

    def test_project_and_privacy_are_enforced_on_all_complete_records(self):
        bridge.append_event(self.bus, self.event())
        before = self.bus.read_bytes()
        for changes in ({"project": "other-project"}, {"privacy": "work-private"}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(bridge.BridgeError, "mismatch"):
                    bridge.append_event(self.bus, self.event(**changes))
                with self.assertRaisesRegex(bridge.BridgeError, "mismatch"):
                    bridge.read_bus(self.bus, changes.get("project", "home-infra"), changes.get("privacy", "personal"))
        self.assertEqual(self.bus.read_bytes(), before)
        with self.bus.open("ab") as stream:
            stream.write((json.dumps(self.event(project="other-project")) + "\n").encode())
        with self.assertRaisesRegex(bridge.BridgeError, "line 2"):
            self.read()

    def test_ack_requires_an_existing_target(self):
        bridge.append_event(self.bus, self.event())
        with self.assertRaisesRegex(bridge.BridgeError, "requires in_reply_to"):
            bridge.append_event(self.bus, self.event(kind="ack"))
        with self.assertRaisesRegex(bridge.BridgeError, "not present"):
            bridge.append_event(self.bus, self.event(kind="ack", in_reply_to=str(uuid.uuid4())))

    def test_duplicate_event_is_rejected_without_modification(self):
        event = self.event()
        bridge.append_event(self.bus, event)
        before = self.bus.read_bytes()
        with self.assertRaisesRegex(bridge.BridgeError, "already exists"):
            bridge.append_event(self.bus, event)
        self.assertEqual(self.bus.read_bytes(), before)

    def test_cli_body_file_and_read_cursor(self):
        first = self.event()
        bridge.append_event(self.bus, first)
        body_file = Path(self.temp.name) / "packet.md"
        body_file.write_text("Use literal `backticks` and $(commands).\nNo execution.\n")
        base = ["--bus", str(self.bus), "--project", "home-infra", "--privacy", "personal"]
        result = subprocess.run([sys.executable, str(SCRIPT), "append", *base, "--sender", "codex",
                                 "--recipient", "pi-home-infra", "--kind", "message", "--body-file",
                                 str(body_file), "--correlation-id", "ao1-omarchy"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)["event"]
        self.assertEqual(event["body"], body_file.read_text())
        self.assertEqual(event["correlation_id"], "ao1-omarchy")
        result = subprocess.run([sys.executable, str(SCRIPT), "read", *base, "--after-event-id",
                                 first["event_id"], "--limit", "1"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        read = json.loads(result.stdout)
        self.assertEqual(read["events"], [event])
        self.assertEqual(read["last_event_id"], event["event_id"])
        self.assertFalse(read["has_more"])


if __name__ == "__main__":
    unittest.main()
