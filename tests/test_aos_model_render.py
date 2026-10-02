#!/usr/bin/env python3
"""Tests for bin/aos-model/render (model-profile.v1 → harness config fragments).

Covers: stdout cleanliness, schema rejection (incl. typed stdin rejection),
each harness fragment, MoA rejection on pi/claude, --check verdicts, usage
errors, and the dry-by-design contract (never writes config files).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "bin" / "aos-model" / "render"


def single_profile(**overrides: object) -> dict:
    profile: dict = {
        "schema": "model-profile.v1",
        "id": "test-single-a",
        "kind": "single",
        "provider": "openai",
        "model": "gpt-5.5",
        "effort": "high",
        "rung": "primary",
        "context_tokens": 400000,
        "cost": {"in_per_mtok": 1.25, "out_per_mtok": 10.0},
        "roles_known_good": ["implement", "review"],
        "harness_support": {"pi": True, "hermes": True, "claude": True, "codex": True},
        "moa": None,
        "status": "candidate",
        "verdict_ref": None,
    }
    profile.update(overrides)
    return profile


def moa_profile(**overrides: object) -> dict:
    profile: dict = {
        "schema": "model-profile.v1",
        "id": "test-moa-a",
        "kind": "moa",
        "provider": "openai",
        "model": "gpt-5.5",
        "effort": None,
        "rung": "primary",
        "context_tokens": None,
        "cost": {"in_per_mtok": None, "out_per_mtok": None},
        "roles_known_good": ["orchestrate"],
        "harness_support": {"pi": True, "hermes": True, "claude": True, "codex": True},
        "moa": {
            "proposers": ["test-single-a", "test-single-b"],
            "aggregator": "test-judge",
            "rounds": 2,
        },
        "status": "candidate",
        "verdict_ref": None,
    }
    profile.update(overrides)
    return profile


def run(argv: list[str], stdin_text: str | None = None, cwd: str | None = None):
    return subprocess.run(
        [str(RENDER), *argv],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def run_with_profile(profile: dict, argv: list[str]):
    """Run render with the profile on stdin ('-')."""
    return run([*argv, "-"], stdin_text=json.dumps(profile))


class RenderContractTest(unittest.TestCase):
    """Shared assertions: exit codes, stdout cleanliness, typed stderr."""

    def assert_success(self, proc: subprocess.CompletedProcess, expected: dict) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "", "stderr must stay empty on success")
        self.assertEqual(json.loads(proc.stdout), expected)

    def assert_profile_error(self, proc: subprocess.CompletedProcess, code: str) -> dict:
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stdout, "", "stdout must stay empty on profile errors")
        payload = json.loads(proc.stderr)
        self.assertEqual(payload["error"], code)
        return payload


class StdoutCleanlinessTest(RenderContractTest):
    def test_single_json_object_no_trailing_prose(self):
        proc = run_with_profile(single_profile(), ["--harness", "pi"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # stdout must be exactly one JSON document (whitespace aside)
        self.assertEqual(json.loads(proc.stdout), json.loads(proc.stdout))
        json.loads(proc.stdout)  # would raise if multi-doc / trailing prose
        self.assertEqual(proc.stderr, "")

    def test_no_diagnostics_on_success_stderr_empty(self):
        for harness in ("pi", "hermes", "claude"):
            proc = run_with_profile(single_profile(), ["--harness", harness])
            self.assertEqual(proc.stderr, "", harness)
            self.assertEqual(proc.returncode, 0, proc.stderr)


class HarnessFragmentTest(RenderContractTest):
    def test_pi_fragment(self):
        proc = run_with_profile(single_profile(), ["--harness", "pi"])
        self.assert_success(
            proc,
            {
                "defaultProvider": "openai",
                "defaultModel": "gpt-5.5",
                "enabledModels": ["gpt-5.5"],
            },
        )

    def test_hermes_fragment(self):
        proc = run_with_profile(single_profile(), ["--harness", "hermes"])
        self.assert_success(
            proc,
            {"llm": {"provider": "openai", "model": "gpt-5.5"}, "fallback_model": []},
        )

    def test_claude_fragment(self):
        proc = run_with_profile(single_profile(), ["--harness", "claude"])
        self.assert_success(proc, {"args": ["--model", "gpt-5.5"]})

    def test_file_input_matches_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(single_profile()), encoding="utf-8")
            via_file = run(["--harness", "hermes", str(path)])
            via_stdin = run_with_profile(single_profile(), ["--harness", "hermes"])
        self.assertEqual(via_file.returncode, 0, via_file.stderr)
        self.assertEqual(via_file.stdout, via_stdin.stdout)


class MoaTest(RenderContractTest):
    def test_moa_rejected_pi(self):
        proc = run_with_profile(moa_profile(), ["--harness", "pi"])
        payload = self.assert_profile_error(proc, "moa_unsupported_harness")
        self.assertEqual(payload["kind"], "moa")
        self.assertEqual(payload["harness"], "pi")

    def test_moa_rejected_claude(self):
        proc = run_with_profile(moa_profile(), ["--harness", "claude"])
        payload = self.assert_profile_error(proc, "moa_unsupported_harness")
        self.assertEqual(payload["harness"], "claude")

    def test_moa_hermes_provider_overlay(self):
        proc = run_with_profile(moa_profile(), ["--harness", "hermes"])
        self.assert_success(
            proc,
            {
                "llm": {"provider": "moa", "model": "gpt-5.5"},
                "fallback_model": [],
                "moa": {
                    "proposers": ["test-single-a", "test-single-b"],
                    "aggregator": "test-judge",
                    "rounds": 2,
                },
            },
        )


class SchemaRejectionTest(RenderContractTest):
    def test_missing_required_field_rejected(self):
        profile = single_profile()
        del profile["rung"]
        proc = run_with_profile(profile, ["--harness", "pi"])
        payload = self.assert_profile_error(proc, "schema_validation")
        self.assertTrue(payload["errors"])

    def test_bad_enum_rejected(self):
        proc = run_with_profile(single_profile(status="live"), ["--check"])
        self.assertEqual(proc.returncode, 1)
        verdict = json.loads(proc.stdout)
        self.assertFalse(verdict["valid"])

    def test_kind_single_with_moa_object_rejected(self):
        proc = run_with_profile(
            single_profile(moa={"proposers": ["a"], "aggregator": "b", "rounds": 1}),
            ["--harness", "pi"],
        )
        self.assert_profile_error(proc, "schema_validation")

    def test_kind_moa_with_null_moa_rejected(self):
        proc = run_with_profile(moa_profile(moa=None), ["--harness", "hermes"])
        self.assert_profile_error(proc, "schema_validation")

    def test_non_x_extra_field_rejected(self):
        proc = run_with_profile(single_profile(notes="nope"), ["--check"])
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)["valid"])

    def test_x_prefixed_extension_accepted(self):
        proc = run_with_profile(single_profile(x_notes="ok", x_owner="fleet"), ["--check"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["valid"])

    def test_invalid_json_stdin_rejected_typed(self):
        proc = run(["--harness", "pi", "-"], stdin_text="{not json")
        self.assert_profile_error(proc, "invalid_json")

    def test_empty_stdin_rejected_typed(self):
        proc = run(["--check", "-"], stdin_text="")
        self.assert_profile_error(proc, "invalid_json")

    def test_null_effort_and_costs_accepted(self):
        profile = single_profile(effort=None, cost={"in_per_mtok": None, "out_per_mtok": None})
        proc = run_with_profile(profile, ["--check"])
        self.assertEqual(proc.returncode, 0, proc.stderr)


class CheckTest(RenderContractTest):
    def test_check_valid_verdict(self):
        proc = run_with_profile(single_profile(), ["--check"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(
            json.loads(proc.stdout),
            {"schema": "model-profile.v1", "valid": True, "profile_id": "test-single-a", "kind": "single"},
        )

    def test_check_invalid_verdict_exit_1(self):
        proc = run_with_profile(single_profile(status="live", rung="nope"), ["--check"])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "")
        verdict = json.loads(proc.stdout)
        self.assertFalse(verdict["valid"])
        self.assertEqual(len(verdict["errors"]), 2)

    def test_check_and_harness_mutually_exclusive(self):
        proc = run_with_profile(single_profile(), ["--check", "--harness", "pi"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


class UsageErrorTest(RenderContractTest):
    def test_no_args_usage_exit_2(self):
        proc = run([])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_missing_harness_usage_exit_2(self):
        proc = run_with_profile(single_profile(), [])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_unknown_harness_usage_exit_2(self):
        proc = run_with_profile(single_profile(), ["--harness", "codex"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_apply_not_implemented_usage_exit_2(self):
        proc = run_with_profile(single_profile(), ["--harness", "pi", "--apply"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


class HarnessSupportGateTest(RenderContractTest):
    def test_unsupported_harness_typed_error(self):
        profile = single_profile(harness_support={"pi": False, "hermes": True, "claude": True, "codex": False})
        proc = run_with_profile(profile, ["--harness", "pi"])
        self.assert_profile_error(proc, "harness_unsupported")


class DryByDesignTest(RenderContractTest):
    def test_no_files_written_in_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = set()
            after = set()
            proc = run(["--harness", "pi", "-"], stdin_text=json.dumps(single_profile()), cwd=tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            after = set(p.name for p in Path(tmp).iterdir())
            self.assertEqual(before, after)

    def test_apply_flag_rejected_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(
                ["--harness", "pi", "--apply", "-"],
                stdin_text=json.dumps(single_profile()),
                cwd=tmp,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout, "")
            self.assertEqual(list(Path(tmp).iterdir()), [])


class SchemaFileTest(unittest.TestCase):
    SCHEMA = ROOT / "config" / "aos" / "model-profile.v1.schema.json"

    def test_schema_file_is_valid_json_with_frozen_fields(self):
        schema = json.loads(self.SCHEMA.read_text(encoding="utf-8"))
        required = {
            "schema", "id", "kind", "provider", "model", "effort", "rung",
            "context_tokens", "cost", "roles_known_good", "harness_support",
            "moa", "status", "verdict_ref",
        }
        self.assertTrue(required.issubset(set(schema["required"])))
        self.assertEqual(schema["properties"]["schema"]["const"], "model-profile.v1")


if __name__ == "__main__":
    unittest.main()