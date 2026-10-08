"""Exercise sibling launches with real profile cloning, no auth or live tmux/TUI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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
import json, os, sys, time
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
        data = Path(os.environ["HERMES_AGENTS_DATA_HOME"])
        home = data / args[0]
        if os.environ.get("TEST_REQUIRE_CLAIM"):
            claim = json.loads((data / ".seat-claims" / (args[0] + ".json")).read_text())
            assert claim["phase"] == "reserved"
            os.kill(claim["pid"], 0)
        if os.environ.get("TEST_MATERIALIZE_RELEASE"):
            markers = Path(os.environ["TEST_MATERIALIZING"])
            markers.mkdir(exist_ok=True)
            (markers / args[0]).touch()
            deadline = time.monotonic() + 12
            while not Path(os.environ["TEST_MATERIALIZE_RELEASE"]).exists():
                if time.monotonic() >= deadline:
                    raise SystemExit("test: materialization barrier timed out")
                time.sleep(.025)
        if os.environ.get("TEST_MATERIALIZE_FAIL"):
            raise SystemExit("test: materialization failed")
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("materialized config\\n")
        print(home)
    else:
        raise SystemExit("unexpected backend command: " + cmd)
''')
        self._executable("herm", '''
import json, os, sys, time
from pathlib import Path
home = Path(os.environ["HERMES_HOME"])
data = Path(os.environ["HERMES_AGENTS_DATA_HOME"])
claim = json.loads((data / ".seat-claims" / (home.name + ".json")).read_text())
record = {"home": str(home), "args": sys.argv[1:], "claim": claim,
          "lock_pid": int((home / ".herm-tui.lock").read_text()), "tui_pid": os.getpid()}
for target in (Path(os.environ["TEST_LAUNCH"]), home.parent / ("launch-" + home.name + ".json")):
    temporary = target.with_name(target.name + "." + str(os.getpid()))
    temporary.write_text(json.dumps(record))
    os.replace(temporary, target)
if os.environ.get("TEST_TUI_RELEASE"):
    deadline = time.monotonic() + 12
    while not Path(os.environ["TEST_TUI_RELEASE"]).exists():
        if time.monotonic() >= deadline:
            raise SystemExit("test: TUI barrier timed out")
        time.sleep(.025)
raise SystemExit(7 if os.environ.get("TEST_HERM_FAIL") else 0)
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
    command = list(launch)
    if command[0] == "env":
        command.pop(0)
        while "=" in command[0]:
            command.pop(0)
    profile = command[2]
    assert (Path(os.environ["HERMES_AGENT_PROFILE_PATH"]) / (profile + ".yaml")).is_file()
    Path(os.environ["TEST_TMUX"]).write_text(json.dumps(args))
    claim_path = Path(os.environ["HERMES_AGENTS_DATA_HOME"]) / ".seat-claims" / (profile + ".json")
    Path(os.environ["TEST_TRANSFER"]).write_text(claim_path.read_text())
    if os.environ.get("TEST_TMUX_FAIL"):
        raise SystemExit(9)
    # Simulate tmux's child environment, without touching a real server.
    env = dict(os.environ, TMUX="test-server")
    env.pop("HERMES_SEAT_CLAIM_TOKEN", None)
    env.pop("HERMES_SEAT_CLAIM_PROFILE", None)
    if os.environ.get("TEST_TMUX_ASYNC"):
        # A real detached server returns before the child's launcher starts.
        subprocess.Popen([sys.executable, "-c",
            "import os,sys,time; time.sleep(.2); os.execvpe(sys.argv[1], sys.argv[1:], os.environ)",
            *launch], env=env)
        raise SystemExit(0)
    raise SystemExit(subprocess.run(launch, env=env, timeout=18).returncode)
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
            "TEST_TRANSFER": str(self.root / "transfer.json"),
            "TEST_REQUIRE_CLAIM": "1",
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
        (home / "config.yaml").write_text("held base config\n")

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

    def test_notes_lane_and_alternate_work_profile_keep_their_family(self) -> None:
        lane = "personal-notes-steward-research"
        self._profile(lane, "notes-lane")
        self._hold(lane)
        self._assert_launch(self._run("agents", "up", lane, "--here"), lane + "-a1", "notes-lane")
        alternate = "notes-steward-work"
        self._profile(alternate, "alternate-work")
        self._hold(alternate)
        self._assert_launch(
            self._run("herm-tui-m", "notesw", "--tui", "--here"),
            alternate + "-a1", "alternate-work",
        )
        self.assertFalse((self.data / "work-notes-steward-a1").exists())
        self.assertFalse((self.data / "chief-of-staff-work-a1").exists())

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
        self.assertFalse((self.data / ".seat-claims").exists())

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

    def _wait_for(self, path: Path) -> None:
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.025)
        self.assertTrue(path.exists(), f"barrier missing: {path}")

    def _seat(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.scripts / "alias_seat.py"), *args],
            env=self.env, capture_output=True, text=True, timeout=10,
        )

    def _assert_released(self, profile: str) -> None:
        self.assertFalse((self.data / ".seat-claims" / (profile + ".json")).exists())
        self.assertFalse((self.data / profile / ".herm-tui.lock").exists())

    def test_overlapping_launches_claim_distinct_homes_before_materialization(self) -> None:
        # Each case uses the same contained fixture. The first launch is held
        # inside materialize, then the second starts: this catches a reservation
        # taken only after config writes as well as next-seat's old a1 race.
        cases = (
            ("agents", ("up", "chief-of-staff-work", "--here"), {}),
            ("agents", ("up", "chief-of-staff-work"), {"TMUX": "test-parent"}),
            ("herm-tui-m", ("cosw", "--tui", "--here"), {}),
            ("herm-tui-m", ("cosw", "--tui"), {}),
        )
        base = "chief-of-staff-work"
        self._hold(base)
        held = self.data / base
        before = {name: ((held / name).read_bytes(), (held / name).stat().st_mtime_ns)
                  for name in ("config.yaml", ".herm-tui.lock")}
        for index, (script, args, extra_env) in enumerate(cases):
            with self.subTest(script=script, args=args):
                markers = self.root / f"materializing-{index}"
                materialize_release = self.root / f"materialize-release-{index}"
                tui_release = self.root / f"tui-release-{index}"
                env = dict(self.env, **extra_env,
                           TEST_MATERIALIZING=str(markers),
                           TEST_MATERIALIZE_RELEASE=str(materialize_release),
                           TEST_TUI_RELEASE=str(tui_release))
                workers = []
                records = [self.data / f"launch-{base}-a{i}.json" for i in (1, 2)]
                for record in records:
                    record.unlink(missing_ok=True)
                try:
                    workers.append(subprocess.Popen(
                        [str(self.scripts / script), *args], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        start_new_session=True,
                    ))
                    self._wait_for(markers / (base + "-a1"))
                    workers.append(subprocess.Popen(
                        [str(self.scripts / script), *args], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        start_new_session=True,
                    ))
                    self._wait_for(markers / (base + "-a2"))
                    self.assertEqual(before, {
                        name: ((held / name).read_bytes(), (held / name).stat().st_mtime_ns)
                        for name in before
                    })
                    claims = [json.loads((self.data / ".seat-claims" / f"{base}-a{i}.json").read_text())
                              for i in (1, 2)]
                    self.assertEqual({claim["phase"] for claim in claims}, {"reserved"})
                    self.assertEqual(len({claim["pid"] for claim in claims}), 2)
                    self.assertEqual(len({claim["token"] for claim in claims}), 2)
                    materialize_release.touch()
                    for record in records:
                        self._wait_for(record)
                    launches = [json.loads(record.read_text()) for record in records]
                    self.assertEqual(len({launch["home"] for launch in launches}), 2)
                    self.assertEqual(len({launch["lock_pid"] for launch in launches}), 2)
                    for launch in launches:
                        self.assertEqual(launch["claim"]["pid"], launch["lock_pid"])
                        self.assertEqual(launch["tui_pid"], launch["lock_pid"])
                        self.assertEqual(launch["claim"]["phase"], "active")
                        os.kill(launch["lock_pid"], 0)
                finally:
                    materialize_release.touch()
                    tui_release.touch()
                    outcomes = []
                    timed_out = False
                    for worker in workers:
                        try:
                            stdout, stderr = worker.communicate(timeout=20)
                        except subprocess.TimeoutExpired:
                            timed_out = True
                            try:
                                os.killpg(worker.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            stdout, stderr = worker.communicate(timeout=5)
                        outcomes.append((worker.returncode, stdout, stderr))
                    self.assertFalse(timed_out, str(outcomes))
                    for status, stdout, stderr in outcomes:
                        self.assertEqual(status, 0, stdout + stderr)
                for i in (1, 2):
                    self._assert_released(f"{base}-a{i}")

    def test_tmux_parent_claim_transfers_to_child_not_sibling(self) -> None:
        base = "chief-of-staff-work"
        self.env["TEST_TMUX_ASYNC"] = "1"
        for script, args in (("agents", ("up", base)),
                             ("herm-tui-m", ("cosw", "--tui"))):
            with self.subTest(script=script):
                result = self._run(script, *args)
                self._assert_launch(result, base)
                parent = json.loads((self.root / "transfer.json").read_text())
                child = json.loads((self.root / "launch.json").read_text())["claim"]
                self.assertEqual(parent["phase"], "reserved")
                self.assertEqual(child["phase"], "active")
                self.assertEqual(parent["token"], child["token"])
                self.assertNotEqual(parent["pid"], child["pid"])
                self.assertFalse((self.profiles / (base + "-a1.yaml")).exists())
                self._assert_released(base)

    def test_foreign_transfer_and_old_cleanup_cannot_adopt_or_release_owner(self) -> None:
        base = "chief-of-staff-work"
        owner = str(os.getpid())
        result = self._seat("claim", base, owner)
        self.assertEqual(result.returncode, 0, result.stderr)
        token = result.stdout.strip()
        claim_path = self.data / ".seat-claims" / (base + ".json")
        before = claim_path.read_bytes()
        for args in (("claim", base, owner, "foreign-token"),
                     ("release-claim", base, owner, "foreign-token"),
                     ("release-claim", base, "999999", token)):
            self._seat(*args)
            self.assertEqual(claim_path.read_bytes(), before)
        env = dict(self.env, HERMES_SEAT_CLAIM_PROFILE=base,
                   HERMES_SEAT_CLAIM_TOKEN="foreign-token")
        result = subprocess.run(
            [str(self.scripts / "agents"), "up", base, "--here"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.data / base).exists())
        self.assertFalse((self.root / "launch.json").exists())
        self.assertEqual(claim_path.read_bytes(), before)
        self._seat("release-claim", base, owner, token)
        replacement = self._seat("claim", base, owner).stdout.strip()
        self.assertNotEqual(replacement, token)
        self._seat("release-claim", base, owner, token)
        self.assertEqual(json.loads(claim_path.read_text())["token"], replacement)
        self._seat("release-claim", base, owner, replacement)

    def _seat_code(self, code: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, " + repr(str(self.scripts)) + "); " + code],
            env=self.env if env is None else env, capture_output=True, text=True, timeout=10,
        )

    def test_stale_cleanup_preserves_newer_live_claim_and_nested_lock(self) -> None:
        base = "chief-of-staff-work"
        root = self.data / base
        runtime = root / "profiles" / "custom-runtime"
        runtime.mkdir(parents=True)
        (root / "active_profile").write_text("custom-runtime\n")
        dead = subprocess.Popen([sys.executable, "-c", "pass"], env=self.env)
        dead.wait(timeout=10)
        lock = runtime / ".herm-tui.lock"
        lock.write_text(f"{dead.pid}\n")
        claim_dir = self.data / ".seat-claims"
        claim_dir.mkdir(mode=0o700)
        claim_path = claim_dir / (base + ".json")
        claim_path.write_text(json.dumps({"pid": dead.pid, "token": "stale", "phase": "active"}))
        clean = f"import alias_seat as s; print(s.clear_stale_locks({base!r}))"
        result = self._seat_code(clean)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lock.exists())
        self.assertFalse(claim_path.exists())
        # A newer reservation supersedes the dead generation. Neither stale
        # cleanup nor the previous owner's cleanup may remove it or its lock.
        claim_path.write_text(json.dumps({"pid": dead.pid, "token": "stale", "phase": "active"}))
        lock.write_text(f"{dead.pid}\n")
        result = self._seat("claim", base, str(os.getpid()))
        self.assertEqual(result.returncode, 0, result.stderr)
        token = result.stdout.strip()
        before = claim_path.read_bytes()
        result = self._seat_code(clean)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(claim_path.read_bytes(), before)
        self.assertTrue(lock.exists())
        result = self._seat("activate-claim", base, str(os.getpid()), token, str(runtime))
        self.assertEqual(result.returncode, 0, result.stderr)
        before = claim_path.read_bytes(), lock.read_bytes()
        self._seat("release-claim", base, str(dead.pid), "stale")
        result = self._seat_code(clean)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((claim_path.read_bytes(), lock.read_bytes()), before)
        self._seat("release-claim", base, str(os.getpid()), token)
        self.assertFalse(lock.exists())

    def test_seat_data_root_matches_real_backend_selection(self) -> None:
        shared = self.root / "shared"
        shared.mkdir()
        for overrides in ({}, {"AGENT_SHARED_HOME": str(shared)},
                          {"HERMES_SHARED_PEOPLE_HOME": str(shared)},
                          {"AGENT_SHARED_HOME": str(shared), "HERMES_AGENTS_DATA_HOME": str(self.data)}):
            with self.subTest(overrides=overrides):
                env = dict(self.env, XDG_DATA_HOME=str(self.root / "xdg"))
                env.pop("HERMES_AGENTS_DATA_HOME")
                env.update(overrides)
                result = self._seat_code(
                    "import alias_seat as s, backend_impl as h; "
                    "assert s.data_home() == h._data_home(), (s.data_home(), h._data_home())",
                    env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_launches_release_only_their_claim(self) -> None:
        base = "chief-of-staff-work"
        self._hold(base)
        for failure in ("TEST_ENSURE_FAIL", "TEST_MATERIALIZE_FAIL", "TEST_TMUX_FAIL", "TEST_HERM_FAIL"):
            for script, args in (("agents", ("up", base)),
                                 ("herm-tui-m", ("cosw", "--tui"))):
                with self.subTest(failure=failure, script=script):
                    self.env[failure] = "1"
                    try:
                        result = self._run(script, *args)
                    finally:
                        self.env.pop(failure)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self._assert_released(base + "-a1")
                    self.assertEqual((self.data / base / ".herm-tui.lock").read_text(), str(os.getpid()))
                    self.assertEqual((self.data / base / "config.yaml").read_text(), "held base config\n")

    def test_failed_exec_releases_claim_and_pid_lock(self) -> None:
        base = "chief-of-staff-work"
        # Executable on PATH, but execve fails before the fake TUI can run.
        herm = self.bin / "herm"
        herm.write_text(f"#!{self.root / 'missing-interpreter'}\n")
        for script, args in (("agents", ("up", base, "--here")),
                             ("herm-tui-m", ("cosw", "--tui", "--here"))):
            with self.subTest(script=script):
                result = self._run(script, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("cannot launch", result.stderr)
                self.assertFalse((self.root / "launch.json").exists())
                self._assert_released(base)

    def test_attach_here_rejects_without_launch_or_materialization(self) -> None:
        self._hold("chief-of-staff-work")
        before = (self.data / "chief-of-staff-work" / "config.yaml").read_bytes()
        for attach in (("attach",), ("--attach",)):
            for dry in ((), ("--dry-run",)):
                with self.subTest(attach=attach, dry=dry):
                    result = self._run("herm-tui-m", "cosw", *attach, "--here", *dry)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--here cannot be combined", result.stderr)
                    self.assertFalse((self.root / "launch.json").exists())
                    self.assertFalse((self.root / "tmux.json").exists())
                    self.assertFalse((self.data / ".seat-claims").exists())
                    self.assertFalse((self.data / "chief-of-staff-work-a1").exists())
                    self.assertFalse((self.profiles / "chief-of-staff-work-a1.yaml").exists())
                    self.assertEqual((self.data / "chief-of-staff-work" / "config.yaml").read_bytes(), before)

    def test_missing_profile_fails_without_creating_sibling(self) -> None:
        result = self._run("agents", "up", "chief-of-staff-work-o1", "--here")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.profiles / "chief-of-staff-work-o1-a1.yaml").exists())


if __name__ == "__main__":
    unittest.main()
