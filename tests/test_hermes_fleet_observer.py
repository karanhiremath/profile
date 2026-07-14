from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "bin/hermes-fleet/observer"


def load():
    loader = importlib.machinery.SourceFileLoader("hermes_fleet_observer", str(PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ObserverTest(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def test_metrics_are_low_cardinality_and_redacted(self):
        events = [{
            "schema_version": "sandbox.manager.v1",
            "observed_at": "2026-07-14T06:00:00Z",
            "action": "event-append",
            "project": "fleet",
            "sandbox_id": "high-cardinality-box",
            "request_id": "high-cardinality-request",
            "ok": False,
            "error_kind": "PermissionError",
            "duration_ms": 25,
        }]
        fleet = {"projects": [{
            "name": "fleet",
            "pm": {"name": "fleet-pm", "running": True},
            "pl": {"name": "fleet-impl", "running": False},
        }]}
        value = self.module.metrics(events, fleet, timestamp=1784010000)
        self.assertIn('sandbox_manager_requests_total{action="event-append",ok="false",project="fleet"} 1', value)
        self.assertIn('agent_sessions_active{project="fleet",role="pm",status="running"} 1', value)
        self.assertNotIn("high-cardinality-box", value)
        self.assertNotIn("high-cardinality-request", value)

    def test_audit_skips_malformed_and_foreign_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('\n'.join([
                '{bad',
                json.dumps({"schema_version": "other"}),
                json.dumps({"schema_version": "sandbox.manager.v1", "ok": True}),
            ]) + '\n')
            self.assertEqual(len(self.module.audit(path)), 1)

    def test_snapshot_accepts_only_successful_manager_response(self):
        good = Mock(returncode=0, stdout=json.dumps({"ok": True, "result": {"projects": []}}), stderr="")
        with patch.object(self.module.subprocess, "run", return_value=good):
            self.assertEqual(self.module.snapshot()["projects"], [])
        bad = Mock(returncode=1, stdout="", stderr="denied")
        with patch.object(self.module.subprocess, "run", return_value=bad):
            with self.assertRaisesRegex(RuntimeError, "denied"):
                self.module.snapshot()


if __name__ == "__main__":
    unittest.main()
