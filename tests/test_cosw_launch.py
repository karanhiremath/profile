from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COSW = ROOT / "bin/hermes/cosw"
COSW_S = ROOT / "bin/hermes/cosw-s"
COS_S = ROOT / "bin/hermes/cos-s"


def run_plan(*args: str, env: dict[str, str] | None = None) -> dict[str, str]:
    merged = os.environ.copy()
    merged.pop("COSW_SANDBOX", None)
    merged.pop("HERMES_AGENT_TERMINAL_BACKEND", None)
    merged.pop("TERMINAL_ENV", None)
    if env:
        merged.update(env)
    proc = subprocess.run(
        [str(COSW), "--print-plan", *args],
        check=True,
        capture_output=True,
        text=True,
        env=merged,
    )
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key] = value
    return out


class CoswLaunchPlanTest(unittest.TestCase):
    def test_default_is_host_timeout_free_cursor_grok(self):
        plan = run_plan()
        self.assertEqual(plan["backend"], "local")
        self.assertEqual(plan["sandbox"], "0")
        self.assertEqual(plan["provider"], "cursor")
        self.assertEqual(plan["model"], "grok-4.6:fast")
        self.assertEqual(plan["cursor_sdk"], "1")
        self.assertEqual(plan["timeout_free"], "1")
        self.assertEqual(plan["compose"], "0")
        self.assertEqual(plan["compose_service"], "")
        self.assertTrue(plan["pythonpath"].endswith("timeout-free-cursor-sdk-20260831T1834"))
        self.assertTrue(plan["persona"].endswith("cosw-host-dispatch.md"))

    def test_codex_seat(self):
        plan = run_plan("--codex")
        self.assertEqual(plan["backend"], "local")
        self.assertEqual(plan["provider"], "openai-codex")
        self.assertEqual(plan["model"], "gpt-5.5")
        self.assertEqual(plan["cursor_sdk"], "0")
        self.assertEqual(plan["timeout_free"], "0")
        self.assertEqual(plan["pythonpath"], "")

    def test_xai_grok_seat_is_not_cursor(self):
        plan = run_plan("--xai-grok")
        self.assertEqual(plan["provider"], "xai")
        self.assertEqual(plan["model"], "grok-4.6")
        self.assertEqual(plan["cursor_sdk"], "0")
        self.assertEqual(plan["sandbox"], "0")

    def test_sandbox_opt_in(self):
        plan = run_plan("--sandbox")
        self.assertEqual(plan["backend"], "docker")
        self.assertEqual(plan["sandbox"], "1")
        self.assertEqual(plan["stack"], "work-devboxes")
        self.assertEqual(plan["compose"], "1")
        self.assertEqual(plan["compose_service"], "cosw-sandbox-default")
        self.assertEqual(plan["container"], "cosw-sandbox-default")
        self.assertEqual(plan["persist"], "1")
        self.assertEqual(plan["hostctl"], "1")
        self.assertTrue(plan["persona"].endswith("cosw-dispatch.md"))

    def test_env_sandbox_default(self):
        plan = run_plan(env={"COSW_SANDBOX": "1"})
        self.assertEqual(plan["sandbox"], "1")
        self.assertEqual(plan["backend"], "docker")

    def test_host_flag_overrides_env_sandbox(self):
        plan = run_plan("--host", env={"COSW_SANDBOX": "1"})
        self.assertEqual(plan["sandbox"], "0")
        self.assertEqual(plan["backend"], "local")

    def test_sandbox_stack_list(self):
        proc = subprocess.run(
            [str(COSW), "--sandbox-stack", "list"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("chief-of-staff-work", proc.stdout)
        self.assertIn("cosw-sandbox-default", proc.stdout)

    def test_cosw_s_ls_lists_short_names(self):
        proc = subprocess.run(
            [str(COSW_S), "ls"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cosw", proc.stdout)
        self.assertIn("librarian", proc.stdout)
        self.assertIn("chief-of-staff-work", proc.stdout)
        self.assertNotIn("staging-voice", proc.stdout)

    def test_cos_s_ls_lists_personal_short_names(self):
        proc = subprocess.run(
            [str(COS_S), "ls"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cos", proc.stdout)
        self.assertIn("chief-of-staff", proc.stdout)
        self.assertIn("herm", proc.stdout)
        self.assertIn("dream", proc.stdout)
        self.assertNotIn("chief-of-staff-work", proc.stdout)
        self.assertNotIn("staging-voice", proc.stdout)

    def test_conflicting_seats_fail(self):
        proc = subprocess.run(
            [str(COSW), "--codex", "--xai-grok", "--print-plan"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("conflicting seats", proc.stderr)


if __name__ == "__main__":
    unittest.main()
