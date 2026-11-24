from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_INSTANTIATE = ROOT / "bin/hermes/harness-instantiate"


def run_harness(
    command: str,
    profile_text: str,
    *,
    work_path: bool = False,
    missing_yaml: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        profiles = (
            home / "src/karan.hiremath/agentic/hermes/profiles"
            if work_path else root / "overridden-profiles"
        )
        profiles.mkdir(parents=True)
        (profiles / "seat.yaml").write_text(profile_text, encoding="utf-8")
        fake_bin = root / "bin"
        fake_bin.mkdir()
        python = fake_bin / "python3"
        python.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n',
            encoding="utf-8",
        )
        python.chmod(0o755)
        calls = root / "dispatch.jsonl"
        for name in ("aos", "cai-aos"):
            dispatcher = fake_bin / name
            dispatcher.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "with open(os.environ['DISPATCH_LOG'], 'a') as fh:\n"
                "    fh.write(json.dumps({'entrypoint': Path(sys.argv[0]).name, "
                "'args': sys.argv[1:]}) + '\\n')\n"
                "print('fake dispatch output must not escape')\n",
                encoding="utf-8",
            )
            dispatcher.chmod(0o755)
        dependencies = root / "dependencies"
        dependencies.mkdir()
        if missing_yaml:
            (dependencies / "yaml.py").write_text(
                "raise ImportError('contained missing PyYAML fixture')\n",
                encoding="utf-8",
            )
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.update({
            "HOME": str(home),
            "PATH": str(fake_bin) + os.pathsep + os.defpath,
            "PYTHONPATH": str(dependencies),
            "HERMES_AGENT_PROFILE_PATH": str(profiles),
            "DISPATCH_LOG": str(calls),
        })
        proc = subprocess.run(
            [str(HARNESS_INSTANTIATE), command, "seat"],
            capture_output=True,
            text=True,
            env=env,
        )
        dispatches = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
    return proc, dispatches


def payload_from(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    lines = proc.stdout.splitlines()
    assert len(lines) == 1, proc.stdout
    payload = json.loads(lines[0])
    assert isinstance(payload, dict), proc.stdout
    return payload


def classify(profile_text: str) -> dict[str, object]:
    proc, dispatches = run_harness("classify", profile_text)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert not dispatches, dispatches
    return payload_from(proc)


class HarnessInstantiateTest(unittest.TestCase):
    def test_typed_plane_and_lane_win_over_path(self):
        payload = classify("name: seat\nplane: work\nlane: ops\n")
        self.assertEqual(payload["schema"], "harness-instantiate.v1")
        self.assertEqual(payload["plane"], "work")
        self.assertEqual(payload["lane"], "ops")
        self.assertEqual(payload["reason"], "plane-from-profile")

    def test_path_inference_is_fallback_reason(self):
        payload = classify("name: seat\n")
        self.assertEqual(payload["plane"], "personal")
        self.assertNotIn("lane", payload)
        self.assertEqual(payload["reason"], "plane-inferred-from-path")

    def test_declared_work_prep_outside_work_path_dispatches_only_work(self):
        proc, dispatches = run_harness("prep", "name: seat\nplane: work\nlane: ops\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = payload_from(proc)
        self.assertEqual(payload["plane"], "work")
        self.assertEqual(payload["lane"], "ops")
        self.assertEqual(payload["action"], "handled")
        self.assertEqual(payload["entrypoint"], "cai-aos")
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0]["entrypoint"], "cai-aos")
        args = dispatches[0]["args"]
        self.assertEqual(args[:4], ["instantiate", "--profile", "seat", "--profile-path"])
        self.assertNotIn("/src/karan.hiremath/", args[4])
        self.assertTrue(args[4].endswith("/overridden-profiles/seat.yaml"))

    def test_absent_plane_successfully_infers_and_preps_both_paths(self):
        for work_path, plane, entrypoint in ((False, "personal", "aos"), (True, "work", "cai-aos")):
            for command in ("classify", "prep"):
                with self.subTest(work_path=work_path, command=command):
                    proc, dispatches = run_harness(command, "name: seat\n", work_path=work_path)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    payload = payload_from(proc)
                    self.assertEqual(payload["plane"], plane)
                    if command == "classify":
                        self.assertEqual(payload["reason"], "plane-inferred-from-path")
                        self.assertEqual(dispatches, [])
                    else:
                        self.assertEqual(payload["action"], "handled")
                        self.assertEqual(payload["entrypoint"], entrypoint)
                        self.assertEqual([call["entrypoint"] for call in dispatches], [entrypoint])

    def assert_route_error(self, profile_text, reason, *, missing_yaml=False):
        for command in ("classify", "prep"):
            with self.subTest(command=command, profile_text=profile_text):
                proc, dispatches = run_harness(command, profile_text, missing_yaml=missing_yaml)
                self.assertNotEqual(proc.returncode, 0)
                payload = payload_from(proc)
                self.assertEqual(payload["schema"], "harness-instantiate.v1")
                self.assertEqual(payload["profile"], "seat")
                self.assertEqual(payload["action"], "error")
                self.assertEqual(payload["plane"], "unknown")
                self.assertEqual(payload["entrypoint"], "none")
                self.assertEqual(payload["reason"], reason)
                self.assertNotIn("lane", payload)
                self.assertEqual(dispatches, [])

    def test_missing_pyyaml_never_infers_declared_work_as_personal(self):
        self.assert_route_error("name: seat\nplane: work\n", "pyyaml-required", missing_yaml=True)

    def test_malformed_yaml_never_dispatches(self):
        self.assert_route_error("name: seat\nplane: work\ntiers: [\n", "malformed-yaml")

    def test_declared_invalid_plane_never_infers_or_dispatches(self):
        for value in ("typo", "null", "42", "true", "[]", "{}", "''", "' work '"):
            self.assert_route_error(f"name: seat\nplane: {value}\n", "invalid-plane")

    def test_non_mapping_yaml_is_not_an_absent_plane_manifest(self):
        for text in ("- work\n", "false\n", ""):
            self.assert_route_error(text, "invalid-profile-document")


if __name__ == "__main__":
    unittest.main()
