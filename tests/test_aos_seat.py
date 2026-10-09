"""Tests for `aos seat check` (seat.v1 manifest validation).

Contract under test:
- stdout: exactly one JSON line {"schema":"aos-seat-check.v1","ok":...,
  "manifest":...,"errors":[...]}, nothing else, on both ok and invalid paths.
- exit codes: 0 ok, 1 invalid manifest, 2 usage/environment.
- behavior rule: orchestrate forbids code.write/infra.mutate capabilities and
  write-capable toolsets (file, code_execution).
- schema: config/aos/seat.v1.schema.json (JSON Schema 2020-12); the CLI uses a
  builtin validator, cross-checked here against the `jsonschema` library when
  it is importable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AOS = ROOT / "bin" / "aos"
SCHEMA = ROOT / "config" / "aos" / "seat.v1.schema.json"

VALID_MANIFEST = """\
name: research-seat
node_type: seat
behavior: [orchestrate]
plane: personal
lane: research
capabilities: [read, job.enqueue, buffer.apply, review, escalate, graph.own]
tiers:
  - rung: primary
    provider: together
    model: GLM-5.3-Flash
    effort: medium
  - rung: fallback
    provider: openai-codex
    model: gpt-5.5
    effort: high
toolsets: [terminal, file_read, web, todo]
buffers: [sop-orchestrate]
interfaces:
  job: job-bus
surfaces: [tui]
hosts: [home]
"""

VALID_WORK_SEAT = """\
name: chief-of-staff-work
behavior: [orchestrate]
plane: work
lane: ops
tiers:
  - rung: primary
    provider: together
    model: GLM-5.3-Flash
  - rung: candidate
    provider: openai-codex
    model: gpt-6.1-sol
    effort: high
  - rung: candidate
    provider: claude
    model: claude-opus
    effort: xhigh
    x_harness: claude-cli
toolsets: [terminal, file_read, web, todo, memory, delegation]
"""


def run_seat(args, stdin=None, cwd=None, env_extra=None):
    env = dict(os.environ)
    env.pop("SEAT_SCHEMA", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [str(AOS), "seat", *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
        timeout=60,
    )


def write_manifest(text):
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="aos-seat-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return Path(path)


class SeatCheckCliTest(unittest.TestCase):
    def tearDown(self):
        for p in getattr(self, "_tmp_paths", []):
            p.unlink(missing_ok=True)

    def tmp(self, text):
        path = write_manifest(text)
        self._tmp_paths = getattr(self, "_tmp_paths", []) + [path]
        return path

    def parse_stdout(self, proc):
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, f"stdout must be one JSON line, got: {proc.stdout!r}")
        return json.loads(lines[0])

    # -- ok path -----------------------------------------------------------

    def test_valid_manifest_exit0_contract(self):
        path = self.tmp(VALID_MANIFEST)
        proc = run_seat(["check", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertTrue(proc.stdout.endswith("\n"))
        payload = self.parse_stdout(proc)
        self.assertEqual(
            set(payload), {"schema", "ok", "manifest", "errors"}
        )
        self.assertEqual(payload["schema"], "aos-seat-check.v1")
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["manifest"], str(path))

    def test_valid_manifest_from_stdin(self):
        proc = run_seat(["check", "-"], stdin=VALID_MANIFEST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = self.parse_stdout(proc)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["manifest"], "-")

    def test_orchestrate_with_file_read_and_extensions_ok(self):
        path = self.tmp(VALID_WORK_SEAT)
        proc = run_seat(["check", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIs(self.parse_stdout(proc)["ok"], True)

    def test_superset_hermes_style_profile_ok(self):
        # Seat fields may be embedded in a larger harness profile document.
        path = self.tmp(
            "name: some-profile\n"
            "description: harness-owned field\n"
            "llm:\n  provider: cursor\n  model: some-model\n"
            "surface: tui\n"
            "toolsets: [terminal, file, web]\n"
            "persona: |\n  free text with colons: yes\n"
        )
        proc = run_seat(["check", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_works_from_other_cwd(self):
        proc = run_seat(["check", str(self.tmp(VALID_MANIFEST))], cwd=tempfile.gettempdir())
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_null_effort_ok(self):
        path = self.tmp(
            "name: seat\n"
            "tiers:\n  - rung: primary\n    provider: p\n    model: m\n    effort:\n"
        )
        proc = run_seat(["check", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # -- orchestrate behavior rule ------------------------------------------

    def assert_orchestrate_violation(self, text, needle):
        proc = run_seat(["check", "-", ], stdin=text)
        self.assertEqual(proc.returncode, 1)
        payload = self.parse_stdout(proc)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["schema"], "aos-seat-check.v1")
        self.assertTrue(
            any(needle in err for err in payload["errors"]),
            f"expected {needle!r} in {payload['errors']}",
        )

    def test_orchestrate_code_write_capability(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ncapabilities: [read, code.write]\n",
            "capability 'code.write'",
        )

    def test_orchestrate_infra_mutate_capability(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ncapabilities: [infra.mutate]\n",
            "capability 'infra.mutate'",
        )

    def test_orchestrate_file_toolset(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal, file]\n",
            "toolset 'file'",
        )

    def test_orchestrate_code_execution_toolset(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ntoolsets: [code_execution]\n",
            "toolset 'code_execution'",
        )

    def test_all_orchestrate_violations_reported_together(self):
        proc = run_seat(
            ["check", "-"],
            stdin=(
                "name: s\nbehavior: [orchestrate]\n"
                "capabilities: [code.write, infra.mutate]\n"
                "toolsets: [file, code_execution]\n"
            ),
        )
        self.assertEqual(proc.returncode, 1)
        errs = self.parse_stdout(proc)["errors"]
        self.assertEqual(len(errs), 4)
        self.assertEqual(proc.stderr, "")

    def test_non_orchestrate_write_toolsets_ok(self):
        path = self.tmp(
            "name: s\nbehavior: [implement]\n"
            "capabilities: [code.write]\ntoolsets: [file, code_execution]\n"
        )
        proc = run_seat(["check", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # -- schema rejection ----------------------------------------------------

    def assert_invalid(self, text, needle=None):
        proc = run_seat(["check", "-"], stdin=text)
        self.assertEqual(proc.returncode, 1)
        payload = self.parse_stdout(proc)
        self.assertIs(payload["ok"], False)
        self.assertNotEqual(payload["errors"], [])
        self.assertEqual(proc.stderr, "")
        if needle is not None:
            self.assertTrue(
                any(needle in err for err in payload["errors"]),
                f"expected {needle!r} in {payload['errors']}",
            )

    def test_plane_enum_rejected(self):
        self.assert_invalid("name: s\nplane: team\n", "$.plane")

    def test_node_type_enum_rejected(self):
        self.assert_invalid("name: s\nnode_type: hybrid\n", "$.node_type")

    def test_missing_name_rejected(self):
        self.assert_invalid("plane: work\n", "$: missing required property 'name'")

    def test_empty_behavior_rejected(self):
        self.assert_invalid("name: s\nbehavior: []\n", "$.behavior")

    def test_duplicate_behavior_rejected(self):
        self.assert_invalid(
            "name: s\nbehavior: [orchestrate, orchestrate]\n", "duplicate item"
        )

    def test_tier_missing_model_rejected(self):
        self.assert_invalid(
            "name: s\ntiers:\n  - rung: primary\n    provider: p\n",
            "missing required property 'model'",
        )

    def test_tier_bad_rung_rejected(self):
        self.assert_invalid(
            "name: s\ntiers:\n  - rung: boss\n    provider: p\n    model: m\n",
            "$.tiers[0].rung",
        )

    def test_tier_bad_effort_rejected(self):
        self.assert_invalid(
            "name: s\ntiers:\n  - rung: primary\n    provider: p\n    model: m\n    effort: yolo\n",
            "$.tiers[0].effort",
        )

    def test_tier_unknown_property_rejected(self):
        self.assert_invalid(
            "name: s\ntiers:\n  - rung: primary\n    provider: p\n    model: m\n    provder: typo\n",
            "unexpected property 'provder'",
        )

    def test_interfaces_unknown_key_rejected(self):
        self.assert_invalid(
            "name: s\ninterfaces:\n  job: job-bus\n  https: nope\n",
            "unexpected property 'https'",
        )

    def test_interfaces_extension_key_ok(self):
        path = self.tmp("name: s\ninterfaces:\n  job: job-bus\n  x_socket_hint: unix\n")
        self.assertEqual(run_seat(["check", str(path)]).returncode, 0)

    def test_scalar_document_rejected(self):
        self.assert_invalid("just-a-string\n", "$")

    def test_list_document_rejected(self):
        self.assert_invalid("- a\n- b\n", "$")

    def test_yaml_parse_error_is_invalid_not_usage(self):
        proc = run_seat(["check", "-"], stdin="name: [unclosed\n")
        self.assertEqual(proc.returncode, 1)
        payload = self.parse_stdout(proc)
        self.assertIs(payload["ok"], False)
        self.assertTrue(any("yaml parse error" in e for e in payload["errors"]))
        self.assertEqual(proc.stderr, "")

    def test_empty_document_rejected(self):
        proc = run_seat(["check", "-"], stdin="")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(any("empty" in e for e in self.parse_stdout(proc)["errors"]))

    # -- usage / environment (exit 2, no stdout payload) ----------------------

    def assert_usage(self, proc):
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertNotEqual(proc.stderr, "")

    def test_usage_no_arg(self):
        self.assert_usage(run_seat(["check"]))

    def test_usage_extra_args(self):
        self.assert_usage(run_seat(["check", "a.yaml", "b.yaml"]))

    def test_usage_unknown_flag(self):
        self.assert_usage(run_seat(["check", "--json"]))

    def test_usage_unknown_subcommand(self):
        self.assert_usage(run_seat(["frobnicate"]))

    def test_usage_bare_seat(self):
        self.assert_usage(run_seat([]))

    def test_missing_file_is_usage_env(self):
        self.assert_usage(run_seat(["check", "/nonexistent/aos-seat/manifest.yaml"]))

    def test_help_exit0(self):
        proc = run_seat(["check", "--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage: aos seat check", proc.stdout)

    def test_help_no_stdin_consumed(self):
        proc = run_seat(["check", "--help"], stdin="name: s\n")
        self.assertEqual(proc.returncode, 0)

    def test_builtin_unsupported_schema_keyword_is_env_error(self):
        # The builtin validator must refuse schemas it cannot fully check.
        fd, path = tempfile.mkstemp(suffix=".json", prefix="aos-seat-schema-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"type": "object", "propertyNames": {"maxLength": 3}}, fh)
        proc = run_seat(
            ["check", str(self.tmp("name: s\n"))],
            env_extra={"SEAT_SCHEMA": path},
        )
        os.unlink(path)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("unsupported schema keywords", proc.stderr)


@unittest.skipUnless(
    os.environ.get("SKIP_JSONSCHEMA_CROSSCHECK") != "1", "cross-check disabled"
)
class SchemaCrossCheckTest(unittest.TestCase):
    """Cross-check the builtin validator against the real jsonschema library.

    Proves config/aos/seat.v1.schema.json is valid 2020-12 JSON Schema and
    that the CLI's accept/reject decision agrees with it.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("jsonschema library not available")
        cls.jsonschema = jsonschema
        with open(SCHEMA, encoding="utf-8") as fh:
            cls.schema = json.load(fh)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)
        cls.validator.check_schema(cls.schema)

    def test_schema_is_valid_2020_12(self):
        self.assertTrue(True)  # check_schema ran in setUpClass

    def _agrees(self, doc_text, expected_ok):
        doc = json.loads(json.dumps(__import__("yaml").safe_load(doc_text)))
        lib_errors = sorted(self.validator.iter_errors(doc), key=str)
        lib_ok = not lib_errors
        self.assertEqual(
            lib_ok,
            expected_ok,
            f"schema lib disagrees: lib_errors={lib_errors}",
        )
        proc = run_seat(["check", "-"], stdin=doc_text)
        self.assertEqual(proc.returncode, 0 if expected_ok else 1)
        self.assertIs(self.parse_stdout_cli(proc)["ok"], expected_ok)

    @staticmethod
    def parse_stdout_cli(proc):
        return json.loads(proc.stdout.splitlines()[0])

    def test_agreement_on_valid_manifests(self):
        for text in (VALID_MANIFEST, VALID_WORK_SEAT):
            with self.subTest(manifest=text.splitlines()[0]):
                self._agrees(text, True)

    def test_agreement_on_invalid_manifests(self):
        cases = {
            "plane-enum": "name: s\nplane: team\n",
            "tier-rung": "name: s\ntiers:\n  - rung: boss\n    provider: p\n    model: m\n",
            "tier-effort": "name: s\ntiers:\n  - rung: primary\n    provider: p\n    model: m\n    effort: yolo\n",
            "tier-unknown-prop": "name: s\ntiers:\n  - rung: primary\n    provider: p\n    model: m\n    provder: typo\n",
            "missing-name": "plane: work\n",
            "interfaces-unknown": "name: s\ninterfaces:\n  https: nope\n",
            "empty-behavior": "name: s\nbehavior: []\n",
            "scalar-doc": "just-a-string\n",
            "list-doc": "- a\n- b\n",
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                self._agrees(text, False)


if __name__ == "__main__":
    unittest.main()