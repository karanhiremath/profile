from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin/hermes/project_sessions.py"


class ProjectSessionsIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.registry = root / "projects"
        self.profiles = root / "profiles"
        self.bin = root / "bin"
        self.work = root / "work"
        self.events = root / "events"
        for path in (self.registry, self.profiles, self.bin, self.work, self.events):
            path.mkdir()
        self.tmux_state = root / "tmux-sessions"
        self.tmux_log = root / "tmux.log"
        self.tmux_state.write_text("")
        self.tmux_log.write_text("")
        tmux = self.bin / "tmux"
        tmux.write_text(
            """#!/usr/bin/env python3
import os,sys
from pathlib import Path
state=Path(os.environ['FAKE_TMUX_STATE']); log=Path(os.environ['FAKE_TMUX_LOG'])
args=sys.argv[1:]; sessions=set(state.read_text().split())
with log.open('a') as f: f.write(' '.join(args)+'\\n')
if args[0]=='has-session':
    name=args[args.index('-t')+1].split(':',1)[0]; raise SystemExit(0 if name in sessions else 1)
if args[0]=='new-session':
    name=args[args.index('-s')+1]; sessions.add(name); state.write_text('\\n'.join(sorted(sessions))+'\\n'); raise SystemExit(0)
raise SystemExit(0)
"""
        )
        tmux.chmod(0o755)
        agents = self.bin / "agents"
        agents.write_text("#!/bin/sh\nexit 0\n")
        agents.chmod(0o755)
        for name in ("alpha-pm", "beta-pm"):
            (self.profiles / f"{name}.yaml").write_text(f"name: {name}\n")
        self._registry("alpha", "a-pm", "a-impl", "alpha-pm")
        self._registry("beta", "b-pm", "b-impl", "beta-pm")
        base_env = dict(os.environ)
        base_env.pop("TMUX", None)
        self.env = {
            **base_env,
            "PATH": f"{self.bin}:{os.environ.get('PATH', '')}",
            "FAKE_TMUX_STATE": str(self.tmux_state),
            "FAKE_TMUX_LOG": str(self.tmux_log),
            "HERMES_PROJECT_REGISTRY_PATH": str(self.registry),
            "HERMES_AGENT_PROFILE_PATH": str(self.profiles),
            "HERMES_AGENTS_BIN": str(agents),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _registry(self, name: str, pm: str, pl: str, profile: str) -> None:
        data = {
            "name": name,
            "aliases": [name[0]],
            "workdir": str(self.work),
            "pm": {"profile": profile},
            "tmux": {"pm_session": pm, "pl_session": pl, "implementation_session": pl},
            "event_bus": {
                "publish_paths": [{"path": str(self.events / f"{name}.jsonl")}],
                "event_types": ["pm_started", "pm_attached", "pm_action_required"],
            },
        }
        (self.registry / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    def run_script(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], env=self.env, text=True,
            capture_output=True, check=check,
        )

    def test_fresh_registry_discovers_multiple_projects(self):
        value = json.loads(self.run_script("list").stdout)
        self.assertEqual([row["name"] for row in value], ["alpha", "beta"])
        doctor = json.loads(self.run_script("doctor").stdout)
        self.assertTrue(doctor["ok"])
        self.assertEqual(doctor["project_count"], 2)

    def test_co_located_agent_profile_is_not_treated_as_project(self):
        (self.registry / "alpha-pm.yaml").write_text(
            yaml.safe_dump({
                "name": "alpha-pm",
                "llm": {"provider": "test", "model": "test"},
                "surface": "tui",
                "toolsets": ["terminal"],
                "persona": "Coordinate alpha.",
            }, sort_keys=False)
        )
        value = json.loads(self.run_script("list").stdout)
        self.assertEqual([row["name"] for row in value], ["alpha", "beta"])
        doctor = json.loads(self.run_script("doctor").stdout)
        self.assertTrue(doctor["ok"])
        self.assertEqual(doctor["project_count"], 2)

    def test_missing_pm_is_started_then_existing_pm_is_reused(self):
        first = json.loads(self.run_script("ensure-pm", "alpha").stdout)
        second = json.loads(self.run_script("ensure-pm", "alpha").stdout)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        events = [json.loads(line) for line in (self.events / "alpha.jsonl").read_text().splitlines()]
        self.assertEqual([event["kind"] for event in events], ["pm_started", "pm_attached"])
        self.assertIn("new-session -d -s a-pm", self.tmux_log.read_text())

    def test_pm_attaches_to_existing_registered_session(self):
        self.tmux_state.write_text("a-pm\n")
        self.run_script("pm", "alpha")
        log = self.tmux_log.read_text()
        self.assertIn("attach-session -t a-pm", log)
        self.assertNotIn("new-session", log)

    def test_unknown_project_is_actionable(self):
        proc = self.run_script("resolve", "missing", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no such Hermes project: missing", proc.stderr)
        self.assertIn(str(self.registry), proc.stderr)

    def test_missing_registry_fails_closed(self):
        self.env["HERMES_PROJECT_REGISTRY_PATH"] = str(Path(self.tmp.name) / "absent")
        proc = self.run_script("doctor", check=False)
        self.assertNotEqual(proc.returncode, 0)
        value = json.loads(proc.stdout)
        self.assertFalse(value["ok"])
        self.assertIn("Set HERMES_PROJECT_REGISTRY_PATH", value["remediation"])


if __name__ == "__main__":
    unittest.main()
