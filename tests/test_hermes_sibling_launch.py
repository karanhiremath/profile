"""Exercise sibling launches with real profile cloning, no auth or live tmux/TUI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERMES = ROOT / "bin" / "hermes"


class SiblingLaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scripts = self.root / "scripts"
        self.bin = self.root / "bin"
        self.profiles = self.root / "profiles"
        self.data = self.root / "data"
        for directory in (self.scripts, self.bin, self.profiles, self.data):
            directory.mkdir()
        for name in ("agents", "herm-tui-m", "llm-flags.sh", "alias_seat.py"):
            shutil.copy2(HERMES / name, self.scripts / name)
        shutil.copy2(HERMES / "hermes_agents.py", self.scripts / "backend_impl.py")
        (self.scripts / "fork-env.sh").write_text("# No host overlay in tests.\n")
        # Use the real cloning backend. Materialization is deliberately fake:
        # it checks profile existence but never reads/stages credentials.
        (self.scripts / "hermes_agents.py").write_text('''
import json, os, sys
from pathlib import Path
import yaml
import backend_impl as ha
cmd, *args = sys.argv[1:]
if cmd == "ensure-lane":
    if os.environ.get("TEST_ENSURE_FAIL"):
        raise SystemExit("test: profile directory is read-only")
    print(ha.ensure_lane_profile(*args))
else:
    profile = yaml.safe_load(ha.find_profile(args[0]).read_text())
    if cmd == "resolve":
        print(json.dumps(profile))
    elif cmd == "materialize":
        home = Path(os.environ["HERMES_AGENTS_DATA_HOME"]) / args[0]
        home.mkdir(parents=True, exist_ok=True)
        print(home)
    else:
        raise SystemExit("unexpected backend command: " + cmd)
''')
        self._executable("herm", '''
import json, os, sys
from pathlib import Path
Path(os.environ["TEST_LAUNCH"]).write_text(json.dumps({
    "home": os.environ["HERMES_HOME"], "args": sys.argv[1:]
}))
''')
        self._executable("hermes", '''
import os, sys
os.execv(os.environ["TEST_HERM"], [os.environ["TEST_HERM"], *sys.argv[1:]])
''')
        self._executable("tmux", '''
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
if args[0] == "has-session":
    raise SystemExit(0 if args[-1] == os.environ.get("TEST_BUSY_SESSION") else 1)
if args[0] == "new-session":
    i = args.index("-c") + 2 if "-c" in args else args.index("-n") + 2
    launch = args[i:]
    profile = launch[2]
    assert (Path(os.environ["HERMES_AGENT_PROFILE_PATH"]) / (profile + ".yaml")).is_file()
    Path(os.environ["TEST_TMUX"]).write_text(json.dumps(args))
    # Simulate tmux's child environment, without touching a real server.
    env = dict(os.environ, TMUX="test-server")
    raise SystemExit(subprocess.run(launch, env=env).returncode)
if args[0] in ("attach-session", "switch-client"):
    raise SystemExit(0)
raise SystemExit(1)
''')
        venv = self.root / "venv"
        (venv / "bin").mkdir(parents=True)
        python = venv / "bin" / "python"
        python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
        python.chmod(0o755)
        # Whitelist environment: no operator credentials or overlay paths.
        self.env = {
            "HOME": str(self.root), "PATH": f"{self.bin}:/usr/bin:/bin",
            "HERMES_PYTHON_VENV": str(venv), "HERMES_PYTHON": sys.executable,
            "HERMES_SHIM_DIR": str(self.bin),
            "HERMES_TOOLCHAIN_HOME": str(self.root / "toolchain"),
            "HERMES_AGENT_PROFILE_PATH": str(self.profiles),
            "HERMES_AGENTS_DATA_HOME": str(self.data),
            "AGENTIC_HOST_CLASS": "work",
            "TEST_LAUNCH": str(self.root / "launch.json"),
            "TEST_TMUX": str(self.root / "tmux.json"),
            "TEST_HERM": str(self.bin / "herm"),
        }
        self._profile("chief-of-staff-work")
        self._profile("chief-of-staff")

    def _executable(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(0o755)

    def _profile(self, name: str, marker: str = "inherited") -> None:
        (self.profiles / f"{name}.yaml").write_text(
            f"name: {name}\nsurface: tui\nmarker: {marker}\n"
        )

    def _hold(self, name: str) -> None:
        home = self.data / name
        home.mkdir()
        (home / ".herm-tui.lock").write_text(str(os.getpid()))

    def _run(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.scripts / script), *args], env=self.env,
            capture_output=True, text=True, timeout=20,
        )

    def _assert_launch(
        self, result: subprocess.CompletedProcess[str], name: str, marker: str = "inherited",
    ) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launched = json.loads((self.root / "launch.json").read_text())
        self.assertEqual(launched["home"], str(self.data / name))
        text = (self.profiles / f"{name}.yaml").read_text()
        self.assertIn(f"name: {name}\n", text)
        self.assertIn(f"marker: {marker}", text)

    def test_busy_home_creates_profile_before_materialize(self) -> None:
        for base in ("chief-of-staff-work", "chief-of-staff"):
            with self.subTest(base=base):
                self._hold(base)
                self._assert_launch(self._run("agents", "up", base, "--here"), base + "-a1")
                self.assertEqual((self.data / base / ".herm-tui.lock").read_text(), str(os.getpid()))

    def test_existing_sibling_profile_is_not_overwritten(self) -> None:
        self._hold("chief-of-staff-work")
        name = "chief-of-staff-work-a1"
        self._profile(name, "custom")
        path = self.profiles / f"{name}.yaml"
        before = path.read_bytes(), path.stat().st_mtime_ns
        result = self._run("agents", "up", "chief-of-staff-work", "--here")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_held_sibling_skipped(self) -> None:
        self._hold("chief-of-staff-work")
        self._hold("chief-of-staff-work-a1")
        self._assert_launch(
            self._run("agents", "up", "chief-of-staff-work", "--here"),
            "chief-of-staff-work-a2",
        )

    def test_nested_lane_inherits_lane_not_family(self) -> None:
        base = "chief-of-staff-work-o1"
        self._profile(base, "lane-specific")
        self._hold(base)
        self._assert_launch(
            self._run("agents", "up", base, "--here"), base + "-a1", "lane-specific",
        )

    def test_busy_tmux_session_creates_profile_before_child_launch(self) -> None:
        self.env["TEST_BUSY_SESSION"] = "cosw"
        self._assert_launch(
            self._run("agents", "up", "chief-of-staff-work"), "chief-of-staff-work-a1",
        )
        args = json.loads((self.root / "tmux.json").read_text())
        self.assertEqual(args[args.index("-s") + 1], "cosw-a1")

    def test_mobile_creates_profile_before_tmux_launch(self) -> None:
        self._hold("chief-of-staff-work")
        self._assert_launch(self._run("herm-tui-m", "cosw"), "chief-of-staff-work-a1")

    def test_mobile_dry_run_does_not_create_profile_or_home(self) -> None:
        self._hold("chief-of-staff-work")
        result = self._run("herm-tui-m", "cosw", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("profile=chief-of-staff-work-a1", result.stdout)
        self.assertFalse((self.profiles / "chief-of-staff-work-a1.yaml").exists())
        self.assertFalse((self.data / "chief-of-staff-work-a1").exists())

    def test_clone_failure_stops_before_launch(self) -> None:
        self._hold("chief-of-staff-work")
        self.env["TEST_ENSURE_FAIL"] = "1"
        for script, args in (
            ("agents", ("up", "chief-of-staff-work", "--here")),
            ("herm-tui-m", ("cosw",)),
        ):
            with self.subTest(script=script):
                result = self._run(script, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("profile directory is read-only", result.stderr)
                self.assertFalse((self.root / "launch.json").exists())
                self.assertFalse((self.root / "tmux.json").exists())

    def test_missing_profile_fails_without_creating_sibling(self) -> None:
        result = self._run("agents", "up", "chief-of-staff-work-o1", "--here")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.profiles / "chief-of-staff-work-o1-a1.yaml").exists())


if __name__ == "__main__":
    unittest.main()
