"""Offline contract, safety and actual CLI pipeline regression tests."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from aos_voice import cli, core, renderer  # noqa: E402

FIXTURE = core.decode((ROOT / "fixtures/catalog.json").read_text())
REQUEST = core.decode((ROOT / "fixtures/request.json").read_text())
SENTINEL = "PRIVATE-TRANSCRIPT-DO-NOT-EMIT"


def bound(
    target: str = "remote-worker", revision: int = 3, domain: str = "personal"
) -> dict:
    return core.bind(core.initial(FIXTURE), target, revision, domain)


def joined() -> dict:
    return core.connection(bound(), "connect")


class Contracts(unittest.TestCase):
    def test_remote_conference_cascade(self) -> None:
        result = core.FakeManagedAgent().call(joined(), REQUEST)
        self.assertEqual(
            result["receipt"]["route"],
            ["controller", "project-manager", "project-lead", "remote-worker"],
        )
        self.assertEqual(result["receipt"]["acks"][-1]["state"], "simulated_completed")
        self.assertFalse(result["receipt"]["executed"])
        self.assertEqual(result["binding"]["route"][-1]["tmux"]["server"], "toolbox")
        self.assertEqual(core.state(result), result)

    def test_domains_require_explicit_binding(self) -> None:
        with self.assertRaises(core.Rejected):
            bound("work-controller", 1, "personal")
        result = bound("work-controller", 1, "work")
        self.assertEqual(result["binding"]["domain"], "work")

    def test_parent_domain_mismatch(self) -> None:
        value = deepcopy(FIXTURE)
        value["targets"][3]["domain"] = "work"
        with self.assertRaises(core.Rejected):
            core.initial(value)

    def test_personal_cannot_load_work_profile(self) -> None:
        for name in ("chief-of-staff-work", "cosw", "work-cos", "cos-work"):
            with self.subTest(name=name):
                value = deepcopy(FIXTURE)
                value["targets"][0]["profile"] = name
                with self.assertRaises(core.Rejected):
                    core.initial(value)

    def test_capabilities_cannot_widen(self) -> None:
        value = deepcopy(FIXTURE)
        value["targets"][1]["capabilities"] = ["status"]
        with self.assertRaises(core.Rejected):
            core.initial(value)

    def test_plain_shell_is_observe_only(self) -> None:
        value = core.connection(bound("plain-shell", 1), "connect")
        request = dict(REQUEST, target="plain-shell", generation=1, verb="observe")
        self.assertEqual(
            core.FakeManagedAgent().call(value, request)["receipt"]["verb"], "observe"
        )
        request.update(verb="steer", text="Never type this into a shell")
        with self.assertRaises(core.Rejected):
            core.FakeManagedAgent().call(value, request)
        catalog = deepcopy(FIXTURE)
        catalog["targets"][4]["capabilities"].append("steer")
        with self.assertRaises(core.Rejected):
            core.initial(catalog)

    def test_stale_generation_and_boolean_generation(self) -> None:
        with self.assertRaises(core.Rejected):
            core.bind(core.initial(FIXTURE), "controller", True, "personal")
        for revision in (2, True, 0):
            with self.subTest(revision=revision), self.assertRaises(core.Rejected):
                core.bind(core.initial(FIXTURE), "remote-worker", revision, "personal")
        with self.assertRaises(core.Rejected):
            core.FakeManagedAgent().call(joined(), dict(REQUEST, generation=2))

    def test_snapshot_generation_rejects_boolean_alias(self) -> None:
        value = joined()
        value["binding"]["route"][0]["generation"] = True
        with self.assertRaises(core.Rejected):
            core.state(value)

    def test_steering_text_is_bounded_before_trimming(self) -> None:
        for text in ("", "  ", "x" * 4097, " " * 4096 + "x"):
            with self.subTest(length=len(text)), self.assertRaises(core.Rejected):
                core.FakeManagedAgent().call(
                    joined(), dict(REQUEST, verb="steer", text=text)
                )

    def test_replaced_ancestor_invalidates_binding(self) -> None:
        value = joined()
        value["catalog"]["targets"][0]["generation"] += 1
        with self.assertRaises(core.Rejected):
            core.state(value)

    def test_host_or_tmux_changes_invalidate_binding(self) -> None:
        for key in ("host", "session", "tmux"):
            value = joined()
            node = value["catalog"]["targets"][3]
            node[key] = "replaced" if key != "tmux" else dict(node["tmux"], pane="%999")
            with self.subTest(key=key), self.assertRaises(core.Rejected):
                core.state(value)

    def test_window_focus_cannot_retarget_request(self) -> None:
        for target in ("project-lead", "work-controller", "plain-shell"):
            with self.subTest(target=target), self.assertRaises(core.Rejected):
                core.FakeManagedAgent().call(joined(), dict(REQUEST, target=target))

    def test_leave_before_rebinding(self) -> None:
        with self.assertRaises(core.Rejected):
            core.bind(joined(), "controller", 1, "personal")
        left = core.connection(joined(), "disconnect")
        self.assertEqual(
            core.bind(left, "controller", 1, "personal")["connection"], "disconnected"
        )

    def test_reconnect_does_not_forget_replay(self) -> None:
        value = core.FakeManagedAgent().call(joined(), REQUEST)
        value = core.connection(core.connection(value, "disconnect"), "connect")
        with self.assertRaises(core.Rejected):
            core.FakeManagedAgent().call(value, REQUEST)

    def test_history_is_bounded_without_eviction(self) -> None:
        value = joined()
        value["seen"] = [f"request-{i}" for i in range(128)]
        with self.assertRaises(core.Rejected):
            core.FakeManagedAgent().call(value, REQUEST)

    def test_no_auto_connect(self) -> None:
        with self.assertRaises(core.Rejected):
            core.FakeManagedAgent().call(bound(), REQUEST)
        with self.assertRaises(core.Rejected):
            core.connection(core.initial(FIXTURE), "connect")

    def test_dry_runs_do_not_change_state(self) -> None:
        value = core.bind(core.initial(FIXTURE), "remote-worker", 3, "personal", True)
        self.assertIsNone(value["binding"])
        value = core.connection(bound(), "connect", True)
        self.assertEqual(value["connection"], "disconnected")
        value = core.FakeManagedAgent().call(joined(), REQUEST, True)
        self.assertEqual(value["seen"], [])
        self.assertEqual(value["receipt"]["acks"], [])
        value = core.connection(joined(), "disconnect", True)
        self.assertEqual(value["connection"], "connected")

    def test_text_is_never_returned(self) -> None:
        for verb in ("steer", "draft"):
            request = dict(REQUEST, verb=verb, text=SENTINEL)
            result = core.FakeManagedAgent().call(joined(), request)
            self.assertNotIn(SENTINEL, json.dumps(result))

    def test_unknown_or_destructive_verbs_and_extra_fields(self) -> None:
        for request in (
            dict(REQUEST, verb="shell.exec"),
            dict(REQUEST, verb="cancel"),
            dict(REQUEST, command="rm"),
            dict(REQUEST, text=SENTINEL),
        ):
            with self.subTest(request=request), self.assertRaises(core.Rejected):
                core.FakeManagedAgent().call(joined(), request)

    def test_catalog_rejects_cycles_duplicates_missing_parents(self) -> None:
        values = []
        value = deepcopy(FIXTURE)
        value["targets"][0]["parent"] = "remote-worker"
        values.append(value)
        value = deepcopy(FIXTURE)
        value["targets"][3]["parent"] = "unknown"
        values.append(value)
        value = deepcopy(FIXTURE)
        value["targets"].append(deepcopy(value["targets"][0]))
        values.append(value)
        value = deepcopy(FIXTURE)
        value["targets"][3]["tmux"]["pane"] = "%1"
        values.append(value)
        for value in values:
            with self.subTest(value=value), self.assertRaises(core.Rejected):
                core.initial(value)

    def test_json_parser_is_strict_and_bounded(self) -> None:
        for raw in (
            '{"x":1,"x":2}',
            '{"x":NaN}',
            "[]",
            "prose",
            "x" * (core.LIMIT + 1),
        ):
            with self.subTest(raw=raw[:20]), self.assertRaises(core.Rejected):
                core.decode(raw)

    def test_fake_state_cannot_be_claimed_live(self) -> None:
        value = joined()
        value["mode"] = "live"
        with self.assertRaises(core.Rejected):
            core.state(value)

    def test_renderer_is_only_a_byte_seam(self) -> None:
        view = renderer.FakeRenderer("remote-worker", 3)
        adapter: renderer.Renderer = view
        raw = b"\x1b[?1049h" + "hello \u03bb\U0001f30d".encode() + b"\x1b[?1049l"
        for byte in raw:
            adapter.feed("remote-worker", 3, bytes([byte]))
        adapter.resize("remote-worker", 3, 120, 40)
        self.assertEqual(bytes(view.data), raw)
        self.assertEqual(view.summary()["rows"], 40)
        self.assertNotIn("hello", json.dumps(view.summary()))
        self.assertFalse(renderer.capabilities()["terminal_rendering"])
        self.assertFalse(renderer.capabilities()["live_ready"])

    def test_renderer_rejects_wrong_target_generation_resize(self) -> None:
        view = renderer.FakeRenderer("remote-worker", 3)
        for target, revision in (
            ("controller", 3),
            ("remote-worker", 2),
            ("remote-worker", True),
        ):
            with (
                self.subTest(target=target, revision=revision),
                self.assertRaises(core.Rejected),
            ):
                view.feed(target, revision, b"data")
        for cols, rows in ((0, 1), (80, 1001), (True, 24)):
            with self.subTest(cols=cols), self.assertRaises(core.Rejected):
                view.resize("remote-worker", 3, cols, rows)
        with self.assertRaises(core.Rejected):
            view.feed("remote-worker", 3, b"x" * 1048577)


class Cli(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.env = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "TMPDIR")
            if key in os.environ
        }

    def invoke(
        self,
        args: list[str],
        value: object = None,
        raw: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "run.py"), *args],
            check=False,
            input=raw
            if raw is not None
            else (json.dumps(value) if value is not None else ""),
            text=True,
            capture_output=True,
            env=self.env | (env or {}),
            timeout=15,
        )

    def request(self, **changes: object) -> Path:
        path = self.dir / "request.json"
        path.write_text(json.dumps(dict(REQUEST, **changes)))
        return path

    def test_cli_e2e_fake_pipeline(self) -> None:
        steps = [
            ("targets", "--catalog", str(ROOT / "fixtures/catalog.json")),
            (
                "bind",
                "--fake",
                "--domain",
                "personal",
                "--target",
                "remote-worker",
                "--generation",
                "3",
            ),
            ("join", "--fake"),
            ("dispatch", "--fake", "--request", str(ROOT / "fixtures/request.json")),
            ("leave", "--fake"),
        ]
        raw = ""
        for args in steps:
            result = self.invoke(list(args), raw=raw)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            raw = result.stdout
            core.state(json.loads(raw))
        self.assertEqual(json.loads(raw)["connection"], "disconnected")
        self.assertEqual(json.loads(raw)["seen"], ["demo-turn-1"])

    def test_status_doctor_renderer_never_claim_live(self) -> None:
        for command in ("status", "doctor", "renderer"):
            result = self.invoke([command])
            self.assertEqual(result.returncode, 0)
            self.assertFalse(json.loads(result.stdout)["live_ready"])
            self.assertEqual(result.stderr, "")

    def test_help_is_diagnostic_only(self) -> None:
        result = self.invoke(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Offline", result.stderr)

    def test_mutations_require_explicit_mode(self) -> None:
        result = self.invoke(["connect"], bound())
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["code"], "invalid_arguments")

    def test_malformed_inputs_do_not_leak(self) -> None:
        for raw in (
            SENTINEL,
            '{"schema":"wrong","secret":"' + SENTINEL + '"}',
            "[]",
            '{"schema":NaN}',
        ):
            result = self.invoke(["join", "--fake"], raw=raw)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["schema"], "aos.voice.error.v1")
            self.assertNotIn(SENTINEL, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_nested_invalid_types_are_sanitized(self) -> None:
        for field in (
            "domain",
            "role",
            "harness",
            "capabilities",
            "tmux",
            "generation",
        ):
            value = deepcopy(FIXTURE)
            value["targets"][0][field] = [SENTINEL]
            result = self.invoke(["targets"], value)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(SENTINEL, result.stdout + result.stderr)

    def test_all_event_env_aliases_fan_out_without_transcripts(self) -> None:
        paths = [self.dir / f"{i}.ndjson" for i in range(4)]
        env = {
            "CARTESIA_EVENT_SINKS": json.dumps(
                [{"type": "file", "path": str(paths[0])}]
            ),
            "CARTESIA_EVENT_BUSES": f"{paths[1]},{paths[2]}",
            "CARTESIA_EVENT_BUS": str(paths[3]),
            "CARTESIA_EVENT_PROFILE": "none",
        }
        result = self.invoke(
            [
                "dispatch",
                "--fake",
                "--request",
                str(self.request(verb="steer", text=SENTINEL)),
            ],
            joined(),
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        records = [json.loads(path.read_text()) for path in paths]
        self.assertTrue(all(record == records[0] for record in records))
        self.assertEqual(records[0]["schema_version"], "cartesia.event.v1")
        self.assertNotIn(SENTINEL, json.dumps(records))
        self.assertNotIn("remote-worker", json.dumps(records))
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout)["receipt"]["status"], "simulated")

    def test_event_file_cannot_be_stdout(self) -> None:
        path = self.dir / "stdout.json"
        with path.open("w") as output:
            result = subprocess.run(
                [sys.executable, str(ROOT / "run.py"), "status"],
                check=False,
                text=True,
                stdout=output,
                stderr=subprocess.PIPE,
                env=self.env | {"CARTESIA_EVENT_BUS": str(path)},
                timeout=15,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(path.read_text())["code"], "event_sink_is_output")

    def test_bash_completions(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "tests/completions.bash")],
            check=False,
            text=True,
            capture_output=True,
            env=self.env,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_emits_no_files(self) -> None:
        result = self.invoke(["status"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_failure_events_do_not_leak_input(self) -> None:
        path = self.dir / "events.ndjson"
        result = self.invoke(
            ["join", "--fake"], raw=SENTINEL, env={"CARTESIA_EVENT_BUS": str(path)}
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(path.read_text())["status"], "failed")
        self.assertNotIn(SENTINEL, path.read_text() + result.stderr + result.stdout)

    def test_event_deduplication(self) -> None:
        path = self.dir / "events.ndjson"
        result = self.invoke(
            ["status"],
            env={"CARTESIA_EVENT_BUS": str(path), "CARTESIA_EVENT_BUSES": str(path)},
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_unsupported_sink_profiles_and_stdout_sinks_fail_closed(self) -> None:
        for env in (
            {"CARTESIA_EVENT_PROFILE": "unknown"},
            {"CARTESIA_EVENT_SINKS": '[{"type":"stdout","path":"ignored"}]'},
            {"CARTESIA_EVENT_SINKS": SENTINEL},
        ):
            result = self.invoke(["status"], env=env)
            self.assertEqual(result.returncode, 2)
            json.loads(result.stdout)
            self.assertNotIn(SENTINEL, result.stderr + result.stdout)

    def test_event_symlink_and_fifo_rejected_without_blocking(self) -> None:
        target = self.dir / "target"
        target.write_text("unchanged")
        link = self.dir / "link"
        link.symlink_to(target)
        fifo = self.dir / "fifo"
        os.mkfifo(fifo)
        for path in (link, fifo):
            result = self.invoke(["status"], env={"CARTESIA_EVENT_BUS": str(path)})
            self.assertEqual(result.returncode, 2)
            json.loads(result.stdout)
        self.assertEqual(target.read_text(), "unchanged")

    def test_invalid_args_and_paths_are_not_echoed(self) -> None:
        for args in ([SENTINEL], ["targets", "--catalog", str(self.dir / SENTINEL)]):
            result = self.invoke(args)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(SENTINEL, result.stderr + result.stdout)

    def test_fake_cli_never_invokes_process_or_network(self) -> None:
        with (
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
            patch.object(
                subprocess, "Popen", side_effect=AssertionError("process forbidden")
            ),
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "stdin", io.StringIO(json.dumps(joined()))),
            redirect_stdout(io.StringIO()) as out,
            redirect_stderr(io.StringIO()) as err,
        ):
            code = cli.main(
                ["dispatch", "--fake", "--request", str(ROOT / "fixtures/request.json")]
            )
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out.getvalue())["receipt"]["executed"])
        self.assertEqual(err.getvalue(), "")

    def test_aos_dispatch_and_shell_pipeline(self) -> None:
        worktree = ROOT.parents[1]
        if not (worktree / "bin/aos").is_file():
            self.skipTest("Repository dispatcher is not part of the standalone package")
        env = self.env | {"PROFILE_DIR": str(worktree)}
        result = subprocess.run(
            [str(worktree / "bin/aos"), "voice", "doctor"],
            check=False,
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["live_ready"])
        result = subprocess.run(
            [str(ROOT / "demo")],
            check=False,
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["receipt"]["route"][-1], "remote-worker"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
