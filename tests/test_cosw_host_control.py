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
        self.assertEqual(value["schema_version"], "sandbox.manager.v1")

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
                return {"schema_version": "sandbox.manager.v1", "id": request["id"], "ok": True}

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
