from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COSW = ROOT / "bin/hermes/cosw"
COSW_S = ROOT / "bin/hermes/cosw-s"
COS_S = ROOT / "bin/hermes/cos-s"

# These plan tests assert host-resolved state (timeout-free worktree,
# work-devbox / personal-devbox helpers). Skip cleanly on hosts that do not
# carry the checkout layout (e.g. CI runners) instead of failing.
_KH_CHECKOUT = Path.home() / "src" / "karan.hiremath"
_TIMEOUT_FREE_WORKTREE = Path.home() / "src" / "hermes-agent-worktrees" / "timeout-free-cursor-sdk-20260831T1834"
_WORK_DEVBOX = _KH_CHECKOUT / "agentic" / "hermes" / "sandboxes" / "work-devbox"
_PERSONAL_DEVBOX = Path.home() / "src" / "hermes" / "sandboxes" / "personal-devbox"

requires_host_checkout = unittest.skipUnless(
    _KH_CHECKOUT.is_dir() and _TIMEOUT_FREE_WORKTREE.is_dir(),
    "host checkout + timeout-free worktree required",
)
requires_work_devbox = unittest.skipUnless(
    _WORK_DEVBOX.exists(), "work-devbox helper required",
)
requires_personal_devbox = unittest.skipUnless(
    _PERSONAL_DEVBOX.exists(), "personal-devbox helper required",
)


def run_plan(
    *args: str,
    env: dict[str, str] | None = None,
    profile_text: str | None = None,
) -> dict[str, str]:
    merged = os.environ.copy()
    merged.pop("COSW_SANDBOX", None)
    merged.pop("HERMES_AGENT_TERMINAL_BACKEND", None)
    merged.pop("TERMINAL_ENV", None)
    if env:
        merged.update(env)

    def invoke() -> dict[str, str]:
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

    if profile_text is None:
        return invoke()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "chief-of-staff-work.yaml").write_text(profile_text, encoding="utf-8")
        merged["HERMES_AGENT_PROFILE_PATH"] = tmp
        return invoke()


DECLARED_TIERS_PROFILE = """\
name: chief-of-staff-work
tiers:
  - rung: primary
    provider: together
    model: zai-org/GLM-5.3-Flash
    effort: medium
  - rung: fallback
    provider: openai-codex
    model: gpt-6.1-sol
    effort: high
  - rung: candidate
    provider: cursor
    model: grok-4.6:fast
"""

NO_MODEL_PROFILE = "name: chief-of-staff-work\n"

LLM_FALLBACK_PROFILE = """\
name: chief-of-staff-work
llm:
  provider: cursor
  model: grok-4.6:fast
  thinking: high
fallback_model:
  - provider: openai-codex
    model: gpt-6.1-sol
"""


@contextmanager
def seat_plan_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        profiles = root / "profiles"
        profiles.mkdir()
        (profiles / "chief-of-staff-work.yaml").write_text(DECLARED_TIERS_PROFILE, encoding="utf-8")
        metadata = {
            "alias": "cosw",
            "profile": "chief-of-staff-work",
            "session": "cosw",
            "home": str(root / "agents/chief-of-staff-work"),
            "runtime_home": str(root / "agents/chief-of-staff-work/profiles/chief-of-staff-work"),
        }
        seat_python = root / "seat-python"
        seat_python.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "assert sys.argv[2:] == ['resolve-profile', 'chief-of-staff-work']\n"
            "sys.stderr.write('contained seat resolver diagnostic\\n')\n"
            f"print(json.dumps({metadata!r}))\n",
            encoding="utf-8",
        )
        seat_python.chmod(0o755)
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("COSW_"):
                env.pop(key)
        env.update({
            "HOME": str(home),
            "XDG_DATA_HOME": str(root / "data"),
            "HERMES_AGENT_PROFILE_PATH": str(profiles),
            "HERMES_PYTHON": str(seat_python),
            "HERMES_AGENT_TERMINAL_BACKEND": "local",
            "COSW_WORK_DEVBOX": str(root / "no-work-devbox"),
            "XAI_API_KEY": "",
        })
        yield env, metadata


def run_plan_json(
    *args: str,
    profile_text: str,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "chief-of-staff-work.yaml").write_text(profile_text, encoding="utf-8")
        merged = os.environ.copy() if env is None else env.copy()
        merged["HERMES_AGENT_PROFILE_PATH"] = tmp
        proc = subprocess.run(
            [str(COSW), "--print-plan", "--json", *args],
            check=True,
            capture_output=True,
            text=True,
            env=merged,
        )
    lines = proc.stdout.splitlines()
    assert len(lines) == 1, proc.stdout
    return json.loads(lines[0])


class CoswLaunchPlanTest(unittest.TestCase):
    def test_profile_tiers_default_to_primary_rung(self):
        plan = run_plan(profile_text=DECLARED_TIERS_PROFILE)
        self.assertEqual(plan["backend"], "local")
        self.assertEqual(plan["sandbox"], "0")
        self.assertEqual(plan["provider"], "together")
        self.assertEqual(plan["model"], "zai-org/GLM-5.3-Flash")
        self.assertEqual(plan["thinking"], "medium")
        self.assertEqual(plan["cursor_sdk"], "0")
        self.assertEqual(plan["timeout_free"], "0")
        self.assertEqual(plan["model_source"], "tiers")
        self.assertEqual(plan["rung"], "primary")
        self.assertTrue(plan["persona"].endswith("cosw-host-dispatch.md"))

    def test_codex_seat(self):
        plan = run_plan("--codex", profile_text=NO_MODEL_PROFILE)
        self.assertEqual(plan["backend"], "local")
        self.assertEqual(plan["provider"], "openai-codex")
        # Default flipped to gpt-6.1-sol in 2567d8c; --gpt-5.5 remains legacy.
        self.assertEqual(plan["model"], "gpt-6.1-sol")
        self.assertEqual(plan["cursor_sdk"], "0")
        self.assertEqual(plan["timeout_free"], "0")
        self.assertEqual(plan["pythonpath"], "")

    def test_xai_grok_seat_is_not_cursor(self):
        plan = run_plan("--xai-grok", profile_text=NO_MODEL_PROFILE)
        self.assertEqual(plan["provider"], "xai")
        self.assertEqual(plan["model"], "grok-4.6")
        self.assertEqual(plan["cursor_sdk"], "0")
        self.assertEqual(plan["sandbox"], "0")

    @requires_work_devbox
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

    @requires_work_devbox
    def test_sandbox_stack_list(self):
        proc = subprocess.run(
            [str(COSW), "--sandbox-stack", "list"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("chief-of-staff-work", proc.stdout)
        self.assertIn("cosw-sandbox-default", proc.stdout)

    @requires_work_devbox
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

    @requires_personal_devbox
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

    def test_model_flag_splits_known_provider(self):
        plan = run_plan("--model", "together/zai-org/GLM-5.3-Flash", profile_text=NO_MODEL_PROFILE)
        self.assertEqual(plan["seat"], "custom")
        self.assertEqual(plan["provider"], "together")
        self.assertEqual(plan["model"], "zai-org/GLM-5.3-Flash")
        self.assertEqual(plan["thinking"], "xhigh")
        self.assertEqual(plan["cursor_sdk"], "0")

    def test_provider_model_thinking_flags(self):
        plan = run_plan(
            "--provider", "openai-codex", "--model", "gpt-5.6-luna", "--thinking", "high",
            profile_text=NO_MODEL_PROFILE,
        )
        self.assertEqual(plan["seat"], "custom")
        self.assertEqual(plan["provider"], "openai-codex")
        self.assertEqual(plan["model"], "gpt-5.6-luna")
        self.assertEqual(plan["thinking"], "high")

    def test_thinking_only_flag_keeps_profile_primary_rung(self):
        plan = run_plan("--thinking", "low", profile_text=DECLARED_TIERS_PROFILE)
        self.assertEqual(plan["provider"], "together")
        self.assertEqual(plan["model"], "zai-org/GLM-5.3-Flash")
        self.assertEqual(plan["thinking"], "low")
        self.assertEqual(plan["model_source"], "tiers")
        self.assertEqual(plan["rung"], "primary")
        self.assertEqual(plan["cursor_sdk"], "0")
        self.assertEqual(plan["timeout_free"], "0")

    def test_llm_fallback_profile_is_source_of_truth(self):
        default_plan = run_plan(profile_text=LLM_FALLBACK_PROFILE)
        self.assertEqual(default_plan["provider"], "cursor")
        self.assertEqual(default_plan["model"], "grok-4.6:fast")
        self.assertEqual(default_plan["model_source"], "llm+fallback_model")
        fallback_plan = run_plan("--codex", profile_text=LLM_FALLBACK_PROFILE)
        self.assertEqual(fallback_plan["provider"], "openai-codex")
        self.assertEqual(fallback_plan["model"], "gpt-6.1-sol")
        self.assertEqual(fallback_plan["rung"], "fallback")

    def test_profile_flag_selects_declared_rung(self):
        plan = run_plan("--codex", profile_text=DECLARED_TIERS_PROFILE)
        self.assertEqual(plan["provider"], "openai-codex")
        self.assertEqual(plan["model"], "gpt-6.1-sol")
        self.assertEqual(plan["thinking"], "high")
        self.assertEqual(plan["model_source"], "tiers")
        self.assertEqual(plan["rung"], "fallback")

    def test_profile_source_rejects_undeclared_model_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "chief-of-staff-work.yaml").write_text(DECLARED_TIERS_PROFILE, encoding="utf-8")
            env = os.environ.copy()
            env["HERMES_AGENT_PROFILE_PATH"] = tmp
            proc = subprocess.run(
                [str(COSW), "--print-plan", "--model", "openai-codex/gpt-5.5"],
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("requested model rung not declared", proc.stderr)

    def test_print_plan_json_is_one_object(self):
        payload = run_plan_json("--codex", profile_text=DECLARED_TIERS_PROFILE)
        self.assertEqual(payload["schema"], "cosw-plan.v1")
        self.assertEqual(payload["provider"], "openai-codex")
        self.assertEqual(payload["model"], "gpt-6.1-sol")
        self.assertEqual(payload["model_source"], "tiers")
        self.assertEqual(payload["rung"], "fallback")
        self.assertIs(payload["sandbox"], False)

    def test_human_plan_retains_seat_metadata_and_resolved_primary(self):
        with seat_plan_fixture() as (env, metadata):
            proc = subprocess.run(
                [str(COSW), "--print-plan"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
        lines = proc.stdout.splitlines()
        self.assertEqual(json.loads(lines[0]), metadata)
        fields = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
        self.assertEqual(fields["profile"], metadata["profile"])
        self.assertEqual(fields["provider"], "together")
        self.assertEqual(fields["model"], "zai-org/GLM-5.3-Flash")
        self.assertEqual(fields["model_source"], "tiers")
        self.assertEqual(fields["rung"], "primary")
        self.assertNotIn("contained seat resolver diagnostic", proc.stdout)

    def test_json_plan_combines_seat_metadata_with_each_resolved_rung(self):
        for args, provider, model, rung in (
            ((), "together", "zai-org/GLM-5.3-Flash", "primary"),
            (("--codex",), "openai-codex", "gpt-6.1-sol", "fallback"),
        ):
            with self.subTest(rung=rung), seat_plan_fixture() as (env, metadata):
                payload = run_plan_json(*args, profile_text=DECLARED_TIERS_PROFILE, env=env)
                self.assertEqual(payload["schema"], "cosw-plan.v1")
                for key, value in metadata.items():
                    self.assertEqual(payload[key], value)
                self.assertEqual(payload["provider"], provider)
                self.assertEqual(payload["model"], model)
                self.assertEqual(payload["rung"], rung)
                self.assertEqual(payload["model_source"], "tiers")
                self.assertIs(payload["sandbox"], False)

    def test_flag_conflicts_with_seat_preset_fail(self):
        proc = subprocess.run(
            [str(COSW), "--codex", "--model", "gpt-5.5", "--print-plan"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("conflicting seat", proc.stderr)


if __name__ == "__main__":
    unittest.main()
