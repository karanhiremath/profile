from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "bin/hermes/cosw-host-control"


def load():
    loader = importlib.machinery.SourceFileLoader("cosw_host_control", str(PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class HostControlTest(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def test_fleet_status_reports_registered_session_liveness(self):
        rows = [{"name": "fleet", "description": "test", "pm_session": "fleet-pm", "pl_session": "fleet-impl"}]
        with patch.object(self.module, "project_command", return_value=rows), patch.object(
            self.module, "tmux_running", side_effect=lambda value: value == "fleet-pm"
        ):
            value = self.module.handle({"id": "r1", "action": "fleet-status", "sandbox_id": "box"})
        project = value["result"]["projects"][0]
        self.assertTrue(project["pm"]["running"])
        self.assertFalse(project["pl"]["running"])
        self.assertEqual(value["schema_version"], "cosw.dispatch.v1")

    def test_event_append_uses_registered_source_and_manager_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            project = {
                "name": "fleet",
                "event_bus": {
                    "event_types": ["decision"],
                    "sources": [{"key": "fleet-events", "path": str(path), "writable": True}],
                },
            }
            request = {
                "id": "r2",
                "action": "event-append",
                "project": "fleet",
                "sandbox_id": "box-1",
                "session_id": "session-1",
                "event": {"kind": "decision", "message": {"role": "assistant", "content": "ready"}},
            }
            with patch.object(self.module, "resolve_project", return_value=project):
                value = self.module.handle(request)
            event = json.loads(path.read_text().strip())
            self.assertEqual(event["project"], "fleet")
            self.assertEqual(event["sandbox"]["id"], "box-1")
            self.assertEqual(value["result"]["source"], "fleet-events")
            self.assertTrue(path.with_name("events.jsonl.lock").exists())

    def test_dispatch_pm_writes_every_registered_bus_and_notifies_correct_pm(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "one.jsonl"
            second = Path(tmp) / "two.jsonl"
            project = {
                "name": "fleet",
                "tmux": {"pm_session": "fleet-pm", "implementation_session": "fleet-impl"},
                "event_bus": {
                    "event_types": ["pm_action_required", "pm_action_acknowledged"],
                    "sources": [
                        {"key": "one", "path": str(first), "writable": True},
                        {"key": "two", "path": str(second), "writable": True},
                    ],
                },
            }
            request = {
                "id": "dispatch-1",
                "action": "dispatch-pm",
                "project": "fleet",
                "message": "register/spawn the replacement worker",
                "handoff": "/tmp/handoff.md",
            }
            with patch.object(self.module, "resolve_project", return_value=project), patch.object(
                self.module,
                "ensure",
                return_value={"project": "fleet", "kind": "pm", "session": "fleet-pm", "created": True},
            ), patch.object(
                self.module,
                "notify_pm",
                return_value={"session": "fleet-pm", "target": "fleet-pm:0.0", "created": True, "delivered": True},
            ) as notify:
                result = self.module.dispatch_pm(request, {"sandbox_id": "chief-of-staff-work"})
            self.assertTrue(result["transport_acknowledged"])
            self.assertEqual(result["pm"]["session"], "fleet-pm")
            self.assertEqual(len(result["event"]["writes"]), 2)
            for path in (first, second):
                event = json.loads(path.read_text())
                self.assertEqual(event["kind"], "pm_action_required")
                self.assertEqual(event["project"], "fleet")
                self.assertEqual(event["handoff_path"], "/tmp/handoff.md")
                self.assertEqual(event["dispatch_id"], result["dispatch_id"])
            self.assertIn(result["dispatch_id"], notify.call_args.args[1])

    def test_dispatch_status_finds_semantic_pm_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            project = {
                "name": "fleet",
                "event_bus": {"sources": [{"key": "events", "path": str(path), "writable": True}]},
            }
            path.write_text(json.dumps({
                "kind": "pm_action_acknowledged",
                "project": "fleet",
                "dispatch_id": "cosw-123",
                "agent_id": "fleet-pm",
                "timestamp": "2026-07-14T00:00:00Z",
            }) + "\n")
            with patch.object(self.module, "resolve_project", return_value=project):
                value = self.module.dispatch_status("fleet", "cosw-123")
            self.assertTrue(value["semantic_acknowledged"])
            self.assertEqual(value["ack"]["agent_id"], "fleet-pm")

    def test_event_append_rejects_secret_bearing_keys(self):
        project = {
            "name": "fleet",
            "event_bus": {
                "event_types": ["decision"],
                "sources": [{"key": "fleet-events", "path": "/tmp/unused", "writable": True}],
            },
        }
        request = {
            "id": "r3",
            "action": "event-append",
            "project": "fleet",
            "event": {"kind": "decision", "access_token": "forbidden"},
        }
        with patch.object(self.module, "resolve_project", return_value=project):
            with self.assertRaisesRegex(ValueError, "denied secret-bearing key"):
                self.module.handle(request)

    def test_audit_hashes_request_without_copying_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audit").mkdir()
            request = {"id": "r4", "action": "notify-pm", "project": "fleet", "message": "private body"}
            self.module.audit(root, request, {"id": "r4", "ok": True}, 0.0, 2005)
            raw = (root / "audit/events.jsonl").read_text()
            self.assertNotIn("private body", raw)
            event = json.loads(raw)
            self.assertEqual(event["peer_uid"], 2005)
            self.assertIn("request_sha256", event)

    def test_expired_request_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "request expired"):
            self.module.identity({"id": "r5", "expires_at": "2020-01-01T00:00:00Z"})

    def test_prepare_keeps_state_and_socket_parent_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            runtime = Path(tmp) / "runtime"
            self.module.prepare(root, runtime)
            for path in (root, root / "requests", root / "responses", root / "audit", runtime):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_process_rejects_a_foreign_socket_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            self.module.prepare(root, Path(tmp) / "runtime")
            response = self.module.process(
                {"id": "r6", "action": "fleet-status"},
                root,
                peer_uid=os.getuid() + 1,
            )
            self.assertFalse(response["ok"])
            self.assertIn("PermissionError", response["error"])

    def test_process_binds_identity_to_the_mounted_manager_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            self.module.prepare(root, Path(tmp) / "runtime")
            seen = {}

            def handler(request):
                seen.update(request)
                return {"schema_version": "cosw.dispatch.v1", "id": request["id"], "ok": True}

            with patch.object(self.module, "handle", side_effect=handler):
                response = self.module.process(
                    {"id": "r7", "action": "fleet-status", "sandbox_id": "spoofed"},
                    root,
                    peer_uid=os.getuid(),
                    authenticated_sandbox_id="chief-of-staff-work",
                )
            self.assertTrue(response["ok"])
            self.assertEqual(seen["sandbox_id"], "chief-of-staff-work")


if __name__ == "__main__":
    unittest.main()
