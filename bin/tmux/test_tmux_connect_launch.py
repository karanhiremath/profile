"""Offline control-client tests; vendor commands are fakes in a private temp PATH."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).parent
FAKE = r"""
import json, os, pathlib, subprocess, sys, time
kind = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["FAKE_ROOT"])
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([kind, args]) + "\n")
mode = os.environ.get("FAKE_MODE", "")
if kind == "ssh":
    if mode == "ssh_error":
        sys.stderr.write("SECRET_TEST stderr")
        sys.exit(7)
    if mode == "timeout":
        time.sleep(3)
        sys.exit(0)
    result = subprocess.run(["/bin/sh", "-c", args[-1]], check=False)
    sys.exit(255 if mode == "reply_lost" else result.returncode)
if kind == "podman":
    if args[:1] != ["exec"]:
        sys.exit(99)
    if mode == "stopped":
        sys.exit(125)
    sys.exit(subprocess.run(args[2:], check=False).returncode)
if kind == "tmux":
    if args[:1] == ["list-sessions"]:
        print("kept: 1 windows")
        sys.exit(0)
    if args[:1] in (["attach-session"], ["switch-client"]):
        sys.exit(0)
    if args[:1] == ["has-session"]:
        sys.exit(0)
    if args[:1] != ["new-session"]:
        sys.exit(99)
    session = args[args.index("-s") + 1]
    if mode == "oversized":
        sys.stderr.write("X" * 70000)
        sys.exit(1)
    if mode == "control_error":
        sys.stderr.write("SECRET_TEST stderr")
        sys.exit(4)
    try:
        fd = os.open(root / ("session-" + session), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        sys.stderr.write("duplicate session: " + session)
        sys.exit(1)
    if mode == "bad_reply":
        print("untrusted reply SECRET_TEST")
    else:
        print(session + "\t%3")
    sys.exit(0)
sys.exit(99)
"""


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmux-launch-test-", dir="/private/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.tool = self.root / "tool"
        self.tool.mkdir()
        for name in ("tmux-connect", "tmux-connect-sandbox.inc"):
            shutil.copyfile(SOURCE / name, self.tool / name)
        (self.tool / "hosts").mkdir()
        (self.tool / "hosts" / "registry.conf").write_text(
            "local|local|kept|test\nremote|first.example,second.example|kept|test\n"
        )
        for name in ("tmux", "ssh", "podman"):
            target = self.bin / name
            target.write_text("#!" + sys.executable + "\n" + FAKE)
            target.chmod(0o700)
        (self.bin / "python3").symlink_to(sys.executable)
        for name in ("dirname", "mkdir", "cat", "tr", "awk", "sed"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.exe = self.root / "native-alias"
        self.exe.write_text("#!/bin/sh\nexit 0\n")
        self.exe.chmod(0o700)
        self.cwd = self.root / "space ' literal; cwd"
        self.cwd.mkdir()
        self.env = {
            "PATH": str(self.bin), "HOME": str(self.root),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "FAKE_ROOT": str(self.root),
            "NATIVE_ACCOUNT": "preserved", "NATIVE_MODEL": "operator-choice",
        }
        self.launch = self.tool / "tmux-connect"

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def run_tool(self, argv, mode="", environment=None):
        env = dict(self.env, FAKE_MODE=mode)
        if environment:
            env.update(environment)
        result = subprocess.run(
            ["/bin/bash", str(self.launch), *argv], env=env,
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertLess(len(result.stdout) + len(result.stderr), 8192)
        return result

    def args(self, host="local", session="fresh", box=None, extra=(), native=()):
        target = ["--sandbox", "--new-argv", host, box, session] if box else [
            "--new-argv", host, session
        ]
        return target + ["--cwd", str(self.cwd), *extra, "--", str(self.exe), *native]

    def receipt(self, result):
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_creation_receipt_and_source_identity(self):
        result = self.run_tool(self.args(extra=("--request-id", "request-1")))
        self.assertEqual(result.returncode, 0)
        receipt = self.receipt(result)
        self.assertEqual(receipt["creation"], "created")
        self.assertEqual(receipt["pane"], "%3")
        self.assertEqual(receipt["attach_argv"], ["tmux-connect", "local", "fresh"])
        self.assertEqual(receipt["request_id"], "request-1")
        self.assertEqual(receipt["source"]["sha256"], hashlib.sha256(self.launch.read_bytes()).hexdigest())
        self.assertEqual(receipt["source"]["sandbox_sha256"],
                         hashlib.sha256((self.tool / "tmux-connect-sandbox.inc").read_bytes()).hexdigest())
        for field in ("native_resume_locator", "first_response", "registration", "heartbeat", "model", "resolved_home"):
            self.assertIsNone(receipt[field])
        self.assertFalse(receipt["interactive_shell_initialized"])
        self.assertEqual(receipt["execution"], "tmux-direct-argv")

    def test_literal_argv_and_cwd_without_shell_injection(self):
        marker = self.root / "injected"
        payload = ["--resume", "native-id", "literal; $(touch " + str(marker) + ")",
                   "quote'\" arg", "line\nargument", chr(96) + "touch nope" + chr(96)]
        result = self.run_tool(self.args(native=payload))
        self.assertEqual(result.returncode, 0)
        argv = self.calls()[0][1]
        self.assertEqual(argv[argv.index("/usr/bin/env") + 1:], ["--", str(self.exe), *payload])
        self.assertEqual(argv[argv.index("-c") + 1], str(self.cwd))
        self.assertNotIn("-A", argv)
        self.assertNotIn("set-option", argv)
        self.assertNotIn("send-keys", argv)
        self.assertFalse(marker.exists())
        self.assertNotIn("native-id", result.stdout)

    def test_existing_alias_inputs_preserved(self):
        for alias, profile in (("cos", "chief-of-staff"), ("cos-m", "chief-of-staff"),
                               ("cosw", "chief-of-staff-work"), ("cosw-m", "chief-of-staff-work")):
            with self.subTest(alias=alias):
                native = ["--lane", "selected", "--model", "chosen/model", "--thinking", "high"]
                result = self.run_tool(self.args(
                    session=alias, extra=("--alias", alias, "--profile", profile), native=native
                ))
                self.assertEqual(result.returncode, 0)
                receipt = self.receipt(result)
                self.assertEqual(receipt["declared_alias"], alias)
                self.assertEqual(receipt["declared_profile"], profile)
                self.assertEqual(self.calls()[-1][1][-len(native):], native)

    def test_agents_up_profile_inputs_preserved(self):
        native = ["up", "existing-profile", "--tui", "--resume", "native-locator"]
        result = self.run_tool(self.args(native=native))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls()[0][1][-len(native):], native)

    def test_native_executable_with_no_cli_args_is_direct_argv(self):
        result = self.run_tool(self.args())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls()[0][1][-3:], ["/usr/bin/env", "--", str(self.exe)])

    def test_host_alias_forwarding_form(self):
        argv = ["local", "--new-argv", "fresh", "--cwd", str(self.cwd), "--", str(self.exe)]
        self.assertEqual(self.run_tool(argv).returncode, 0)

    def test_local_sandbox(self):
        result = self.run_tool(self.args(box="existing-box"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls()[0][0], "podman")
        self.assertEqual(self.calls()[0][1][:3], ["exec", "existing-box", "tmux"])
        self.assertEqual(self.receipt(result)["sandbox"], "existing-box")
        self.assertEqual(self.receipt(result)["attach_argv"],
                         ["tmux-connect", "--sandbox", "local", "existing-box", "fresh"])

    def test_sandbox_alias_forwarding_form(self):
        argv = ["--sandbox", "local", "existing-box", "--new-argv", "fresh",
                "--cwd", str(self.cwd), "--", str(self.exe)]
        self.assertEqual(self.run_tool(argv).returncode, 0)

    def test_remote_argv_preserved_with_one_registered_target(self):
        payload = ["literal; $(false)", "quote'\" value", "multi\nline"]
        result = self.run_tool(self.args(host="remote", native=payload))
        self.assertEqual(result.returncode, 0)
        calls = self.calls()
        self.assertEqual([kind for kind, _ in calls], ["ssh", "tmux"])
        self.assertEqual(calls[0][1][-2], "first.example")
        self.assertEqual(calls[1][1][-len(payload):], payload)

    def test_remote_sandbox(self):
        result = self.run_tool(self.args(host="remote", box="existing-box"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual([kind for kind, _ in self.calls()], ["ssh", "podman", "tmux"])

    def test_duplicate_collision_never_attaches(self):
        self.assertEqual(self.run_tool(self.args()).returncode, 0)
        result = self.run_tool(self.args())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.receipt(result)["creation"], "collision")
        self.assertEqual(len(list(self.root.glob("session-*"))), 1)
        self.assertTrue(all(argv[0] == "new-session" for kind, argv in self.calls() if kind == "tmux"))

    def test_parallel_collision_is_atomic(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_tool(self.args()), range(2)))
        self.assertEqual(sorted(result.returncode for result in results), [0, 1])
        self.assertEqual(len(list(self.root.glob("session-*"))), 1)

    def test_remote_collision_never_falls_back(self):
        self.assertEqual(self.run_tool(self.args(host="remote")).returncode, 0)
        result = self.run_tool(self.args(host="remote"))
        self.assertEqual(self.receipt(result)["creation"], "collision")
        self.assertEqual(len([x for x in self.calls() if x[0] == "ssh"]), 2)
        self.assertTrue(all(x[1][-2] == "first.example" for x in self.calls() if x[0] == "ssh"))

    def test_remote_command_failure_is_sanitized_without_retry(self):
        result = self.run_tool(self.args(host="remote"), mode="ssh_error")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.receipt(result)["creation"], "unknown")
        self.assertNotIn("SECRET_TEST", result.stdout + result.stderr)
        self.assertEqual(len(self.calls()), 1)

    def test_agent_custody_mode_never_falls_back_to_ssh(self):
        for value in ("1", "unsupported"):
            with self.subTest(mode=value):
                result = self.run_tool(self.args(host="remote"),
                                       environment={"TMUX_CONNECT_AGENT_MODE": value})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.receipt(result)["creation"], "not_attempted")
                self.assertEqual(self.receipt(result)["diagnostic"],
                                 "agent_custody_mode_unsupported")
        self.assertEqual(self.calls(), [])

    def test_argv_count_rejected_before_python_or_control_spawn(self):
        (self.bin / "python3").unlink()
        result = self.run_tool(self.args(host="remote", native=["literal"] * 257))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.receipt(result)["diagnostic"], "argv_count_limit")
        self.assertEqual(self.calls(), [])

    def test_argv_bytes_rejected_before_python_or_control_spawn(self):
        (self.bin / "python3").unlink()
        for payload in ("X" * 16385, "é" * 9000):
            with self.subTest(bytes=len(payload.encode())):
                result = self.run_tool(self.args(host="remote", native=[payload]))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.receipt(result)["diagnostic"], "argv_bytes_limit")
                self.assertNotIn(payload, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_reply_lost_after_creation_remains_ambiguous(self):
        result = self.run_tool(self.args(host="remote"), mode="reply_lost")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.receipt(result)["creation"], "unknown")
        self.assertTrue((self.root / "session-fresh").exists())
        self.assertEqual(len([x for x in self.calls() if x[0] == "ssh"]), 1)

    def test_timeout_does_not_retry_or_kill_session(self):
        result = self.run_tool(self.args(host="remote", extra=("--timeout", "1")), mode="timeout")
        self.assertEqual(self.receipt(result)["diagnostic"], "control_timeout")
        self.assertEqual(self.receipt(result)["creation"], "unknown")
        self.assertEqual(len(self.calls()), 1)

    def test_output_is_capped_and_not_echoed(self):
        result = self.run_tool(self.args(), mode="oversized")
        self.assertEqual(self.receipt(result)["diagnostic"], "control_output_limit")
        self.assertLess(len(result.stdout), 2048)

    def test_invalid_reply_is_not_a_creation_proof(self):
        result = self.run_tool(self.args(), mode="bad_reply")
        self.assertEqual(self.receipt(result)["diagnostic"], "unverified_creation_reply")
        self.assertEqual(self.receipt(result)["creation"], "unknown")
        self.assertNotIn("SECRET_TEST", result.stdout)

    def test_stopped_sandbox_has_no_lifecycle_attempt(self):
        result = self.run_tool(self.args(box="existing-box"), mode="stopped")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([kind for kind, _ in self.calls()], ["podman"])
        self.assertEqual(self.calls()[0][1][0], "exec")

    def test_invalid_target_identity_does_not_invoke_controls(self):
        for session in ("-bad", "session:0", "@1", "../x", "bad name", "*"):
            with self.subTest(session=session):
                result = self.run_tool(self.args(session=session))
                self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_invalid_paths_do_not_invoke_controls(self):
        for cwd in ("relative", "/work/../other", "/wild/*", "/line\nbreak"):
            with self.subTest(cwd=cwd):
                argv = ["--new-argv", "local", "fresh", "--cwd", cwd, "--", str(self.exe)]
                self.assertEqual(self.run_tool(argv).returncode, 2)
        argv = self.args()
        argv[-1] = "claude"
        self.assertEqual(self.run_tool(argv).returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_missing_cwd_and_executable_rejected(self):
        result = self.run_tool(["--new-argv", "local", "fresh", "--", str(self.exe)])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_unknown_host_does_not_fall_back(self):
        result = self.run_tool(self.args(host="unknown"))
        self.assertEqual(self.receipt(result)["diagnostic"], "unknown_registered_host")
        self.assertEqual(self.calls(), [])

    def test_missing_python_is_sanitized_and_does_not_launch(self):
        (self.bin / "python3").unlink()
        result = self.run_tool(self.args())
        self.assertEqual(result.returncode, 127)
        self.assertEqual(self.receipt(result)["diagnostic"], "python3_unavailable")
        self.assertEqual(self.calls(), [])

    def test_legacy_existing_local_attach(self):
        result = self.run_tool(["local", "kept"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual([argv[0] for kind, argv in self.calls() if kind == "tmux"],
                         ["has-session", "attach-session"])
        self.assertFalse((self.root / "session-kept").exists())

    def test_legacy_local_list_and_cache(self):
        result = self.run_tool(["--ls", "local"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("kept:", result.stdout)
        self.assertTrue((self.root / "cache/tmux-connect/sessions/local").exists())

    def test_skill_is_generic_and_has_required_frontmatter(self):
        skill = (SOURCE.parents[1] / "cursor/skills/harness-launch/SKILL.md").read_text()
        self.assertTrue(skill.startswith("---\nname: harness-launch\n"))
        for text in ("/Users/", "/home/", "~/src/", "cxis-", "cai-aos-toolbox", "Cartesia"):
            self.assertNotIn(text, skill)


if __name__ == "__main__":
    unittest.main()
