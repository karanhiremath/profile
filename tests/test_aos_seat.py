"""Tests for `aos seat check` (seat.v1 manifest validation).

Contract under test:
- stdout: exactly one JSON line {"schema":"aos-seat-check.v1","ok":...,
  "manifest":...,"errors":[...]}, nothing else, on both ok and invalid paths.
- exit codes: 0 ok, 1 invalid manifest, 2 usage/environment.
- behavior rule: orchestrate forbids code.write/infra.mutate capabilities,
  uncharacterized toolsets, and terminal grants without a bounded allowlist.
- schema: config/aos/seat.v1.schema.json (JSON Schema 2020-12); the CLI uses a
  builtin validator, cross-checked here against the `jsonschema` library when
  it is importable.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import re
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

BOUNDED_TERMINAL = """terminal:
  mode: allowlist
  allowlist:
    - aos help
    - aos seat check --help
    - aos seat check -
"""
VALID_MANIFEST += BOUNDED_TERMINAL

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
VALID_WORK_SEAT += BOUNDED_TERMINAL


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


def terminal_catalog():
    schema = json.loads(SCHEMA.read_text())
    terminal_rule = schema["allOf"][0]["then"]["allOf"][0]["then"]
    policy = terminal_rule["properties"]["terminal"]
    return tuple(policy["properties"]["allowlist"]["items"]["enum"])


def mutation_variants(command):
    return (
        command + "\nwhoami", command + "; touch x", command + " | sh",
        command + " > x", command + " >> x", "env X=1 " + command,
        command + " $(touch x)", command + " `touch x`",
        command + " && aos sync", command + " || touch x",
        command + " & touch x", command + "\r\ntouch x",
        command + " < input", "sh -c '" + command + "'",
    )


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
            "forbidden value 'code.write'",
        )

    def test_orchestrate_infra_mutate_capability(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ncapabilities: [infra.mutate]\n",
            "forbidden value 'infra.mutate'",
        )

    def test_orchestrate_file_toolset(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal, file]\n",
            "got 'file'",
        )

    def test_orchestrate_code_execution_toolset(self):
        self.assert_orchestrate_violation(
            "name: s\nbehavior: [orchestrate]\ntoolsets: [code_execution]\n",
            "got 'code_execution'",
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

    def test_orchestrate_wildcards_composites_and_aliases_rejected(self):
        # No registry lookup or alias expansion may turn an unknown grant
        # into a supported name. Includes composites of otherwise safe tools.
        for toolset in ("all", "*", "terminal,file", "file_read+file",
                        "hermes-cli", "hermes-full", "custom-writer",
                        "file_read+web", "File_Read", " file_read",
                        "skills", "clarify", "tts"):
            with self.subTest(toolset=toolset):
                self.assert_invalid(
                    "name: s\nbehavior: [orchestrate]\ntoolsets: "
                    + json.dumps([toolset]) + "\n", "$.toolsets[0]"
                )

    def test_orchestrate_supported_nonterminal_tools_ok(self):
        for tools in ([], ["file_read", "web", "todo", "memory", "delegation"]):
            with self.subTest(tools=tools):
                proc = run_seat(["check", "-"], stdin=(
                    "name: s\nbehavior: [orchestrate]\ntoolsets: "
                    + json.dumps(tools) + "\n"
                ))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(self.parse_stdout(proc)["ok"])

    def test_orchestrate_terminal_requires_policy(self):
        self.assert_invalid(
            "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\n",
            "missing required property 'terminal'",
        )

    def test_orchestrate_terminal_policy_invalid_shapes(self):
        prefix = "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\n"
        cases = [None, False, "allowlist", [], {},
                 {"mode": "allowlist"}, {"allowlist": ["aos help"]},
                 {"mode": "off", "allowlist": ["aos help"]},
                 {"mode": False, "allowlist": ["aos help"]},
                 {"mode": "allowlist", "allowlist": []},
                 {"mode": "allowlist", "allowlist": "aos help"},
                 {"mode": "allowlist", "allowlist": [1]},
                 {"mode": "allowlist", "allowlist": ["aos help"] * 2},
                 {"mode": "allowlist", "allowlist": ["aos help"], "enabled": False}]
        for policy in cases:
            with self.subTest(policy=policy):
                self.assert_invalid(prefix + "terminal: " + json.dumps(policy) + "\n", "terminal")

    def test_orchestrate_unbounded_or_mutating_patterns_rejected(self):
        for pattern in (".*", "^aos", "^aos.*$", "aos *", "^aos help$",
                        r"\Abash .*\Z", r"\Apython3 .*\Z",
                        r"\Aaos sync\Z", r"\Aaos seat check .*\Z",
                        r"\Aaos help\Z|.*", r"\Aaos help\Z",
                        "literal:aos help", r"re:\Aaos help\Z", "["):
            with self.subTest(pattern=pattern):
                self.assert_invalid(
                    "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\nterminal: "
                    + json.dumps({"mode": "allowlist", "allowlist": [pattern]}) + "\n",
                    "$.terminal.allowlist[0]",
                )

    def test_each_bounded_terminal_command_accepted(self):
        for pattern in ("aos help", "aos seat check --help", "aos seat check -"):
            with self.subTest(pattern=pattern):
                proc = run_seat(["check", "-"], stdin=(
                    "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\nterminal: "
                    + json.dumps({"mode": "allowlist", "allowlist": [pattern]}) + "\n"
                ))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(self.parse_stdout(proc)["ok"])

    def test_typed_terminal_transport_fields_accepted(self):
        for backend in ("local", "ssh", "docker", "modal", "daytona", "singularity"):
            for persist in (True, False):
                with self.subTest(backend=backend, persist=persist):
                    policy = {
                        "mode": "allowlist", "allowlist": list(terminal_catalog()),
                        "backend": backend, "cwd": "/workspace",
                        "docker_image": "example/agent:stable",
                        "docker_persist_across_processes": persist,
                    }
                    proc = run_seat(["check", "-"], stdin=(
                        "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\nterminal: "
                        + json.dumps(policy) + "\n"
                    ))
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertTrue(self.parse_stdout(proc)["ok"])

    def test_malformed_terminal_transport_fields_rejected(self):
        cases = (
            ("backend", False), ("backend", []), ("backend", "unknown"),
            ("cwd", None), ("cwd", []), ("cwd", ""),
            ("docker_image", 1), ("docker_image", ""),
            ("docker_persist_across_processes", "true"),
            ("docker_persist_across_processes", 1),
            ("docker", {"mode": "off"}), ("command", "sh"),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                policy = {"mode": "allowlist", "allowlist": ["aos help"], field: value}
                self.assert_invalid(
                    "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\nterminal: "
                    + json.dumps(policy) + "\n", "terminal",
                )

    def test_bounded_patterns_do_not_match_shell_suffixes(self):
        patterns = terminal_catalog()
        self.assertEqual(set(patterns), {"aos help", "aos seat check --help", "aos seat check -"})
        for command in ("aos help", "aos seat check --help", "aos seat check -"):
            self.assertTrue(any(fnmatch.fnmatchcase(command, p) for p in patterns))
            for altered in mutation_variants(command):
                with self.subTest(command=altered):
                    self.assertFalse(any(fnmatch.fnmatchcase(altered.strip(), p) for p in patterns))

    def test_orchestrate_among_other_behaviors_still_restricted(self):
        self.assert_invalid(
            "name: s\nbehavior: [implement, orchestrate]\ntoolsets: [all]\n",
            "$.toolsets[0]",
        )

    def test_non_orchestrate_terminal_and_unknown_tools_compatibility(self):
        for behavior in ("", "behavior: [implement]\n"):
            proc = run_seat(["check", "-"], stdin=(
                "name: s\n" + behavior
                + "toolsets: [all, custom-tools]\nterminal: {mode: off}\n"
            ))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(self.parse_stdout(proc)["ok"])

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

    def test_nonstring_mapping_keys_rejected_everywhere(self):
        for key in ("1", "true", "2026-10-03", "null"):
            for context in (f"{key}: value\n", f"interfaces:\n  {key}: value\n",
                            "tiers:\n  - rung: primary\n    provider: p\n    model: m\n"
                            + f"    {key}: value\n",
                            f"extension:\n  nested:\n    {key}: value\n"):
                for from_file in (False, True):
                    with self.subTest(key=key, context=context, from_file=from_file):
                        text = "name: s\n" + context
                        proc = (run_seat(["check", str(self.tmp(text))]) if from_file
                                else run_seat(["check", "-"], stdin=text))
                        self.assertEqual(proc.returncode, 1)
                        self.assertEqual(proc.stderr, "")
                        payload = self.parse_stdout(proc)
                        self.assertEqual(set(payload), {"schema", "ok", "manifest", "errors"})
                        self.assertEqual(payload["schema"], "aos-seat-check.v1")
                        self.assertFalse(payload["ok"])
                        self.assertIn("mapping keys must be strings", payload["errors"][0])

    def test_nonjson_yaml_values_rejected(self):
        for value in ("2026-10-03", "2026-10-03T10:00:00Z", "!!binary YQ==",
                      "!!set {a: null}", "!!omap [a: 1]", "!!pairs [a: 1]",
                      ".nan", ".inf", "-.inf"):
            for field in ("extension", "buffers"):
                with self.subTest(value=value, field=field):
                    self.assert_invalid(f"name: s\n{field}: [{value}]\n", "JSON")

    def test_malformed_yaml_timestamp_and_key_rejected(self):
        for text in ("name: s\nx: 2026-99-99\n", "name: s\n? [a, b]\n: value\n"):
            self.assert_invalid(text, "yaml parse error")

    def test_cyclic_yaml_alias_rejected(self):
        for text in ("name: s\nx: &loop [*loop]\n", "&loop {name: s, x: *loop}\n"):
            self.assert_invalid(text, "cyclic YAML alias")

    def test_acyclic_yaml_alias_and_json_extensions_ok(self):
        proc = run_seat(["check", "-"], stdin=(
            "name: s\nx: &shared {count: 1, enabled: true, optional: null}\n"
            "y: [*shared, *shared]\nquoted_date: '2026-10-03'\n"
        ))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.parse_stdout(proc)["ok"])

    def test_deep_yaml_structure_rejected_without_traceback(self):
        self.assert_invalid("name: s\nx: " + "[" * 80 + "0" + "]" * 80 + "\n", "limits")

    def test_expanding_yaml_aliases_bounded(self):
        text = "name: s\nx0: &a0 [0]\n"
        for i in range(1, 15):
            text += f"x{i}: &a{i} [*a{i-1}, *a{i-1}]\n"
        self.assert_invalid(text, "limits")

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

    def test_agreement_on_orchestration_grants(self):
        for toolset in ("all", "*", "file", "code_execution", "hermes-cli", "file_read+file", "unknown"):
            with self.subTest(toolset=toolset):
                self._agrees("name: s\nbehavior: [orchestrate]\ntoolsets: "
                             + json.dumps([toolset]) + "\n", False)
        for capability in ("code.write", "infra.mutate"):
            with self.subTest(capability=capability):
                self._agrees("name: s\nbehavior: [orchestrate]\ncapabilities: "
                             + json.dumps([capability]) + "\n", False)
        self._agrees("name: s\nbehavior: [orchestrate]\ntoolsets: [file_read, delegation]\n", True)
        self._agrees("name: s\ntoolsets: [all]\nterminal: {mode: off}\n", True)
        self._agrees("name: s\nbehavior: [implement]\ntoolsets: [all]\nterminal: {mode: off}\n", True)

    def test_agreement_on_terminal_policy(self):
        prefix = "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\n"
        self._agrees(prefix, False)
        for policy in (None, [], {}, {"mode": "off", "allowlist": [".*"]},
                       {"mode": "allowlist", "allowlist": []},
                       {"mode": "allowlist", "allowlist": ["^aos.*$"]},
                       {"mode": "allowlist", "allowlist": ["aos help"], "mode_override": "off"}):
            with self.subTest(policy=policy):
                self._agrees(prefix + "terminal: " + json.dumps(policy) + "\n", False)
        self._agrees(prefix + BOUNDED_TERMINAL, True)

    def test_agreement_on_terminal_transport_fields(self):
        prefix = "name: s\nbehavior: [orchestrate]\ntoolsets: [terminal]\nterminal: "
        policy = {
            "mode": "allowlist", "allowlist": list(terminal_catalog()),
            "backend": "docker", "cwd": "/workspace",
            "docker_image": "example/agent:stable", "docker_persist_across_processes": True,
        }
        self._agrees(prefix + json.dumps(policy), True)
        for field, value in (("backend", False), ("cwd", []),
                             ("docker_image", 0), ("docker_persist_across_processes", "true")):
            with self.subTest(field=field):
                self._agrees(prefix + json.dumps(dict(policy, **{field: value})), False)


@unittest.skipUnless(os.environ.get("AOS_W1_APPROVAL_SOURCE"), "W1 matcher source not supplied")
class W1MatcherCompatibilityTest(unittest.TestCase):
    """Read-only integration against a separately owned W1 approval source.

    Supply AOS_W1_APPROVAL_SOURCE to verify the finite command catalog against
    the actual matcher. Extract only the pure matcher/helper and its regex
    constant; importing the whole approval module would load live config.
    No terminal commands or approval/config side effects are executed.
    """

    @classmethod
    def setUpClass(cls):
        path = Path(os.environ["AOS_W1_APPROVAL_SOURCE"])
        source = path.read_bytes()
        tree = ast.parse(source, filename=str(path))
        functions = {"_command_matches_terminal_allowlist", "_has_allowlist_shell_operator"}
        constant = "_ALLOWLIST_SHELL_OPERATOR_RE"
        nodes = [node for node in tree.body if (
            isinstance(node, ast.FunctionDef) and node.name in functions
        ) or (
            isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == constant for target in node.targets
            )
        )]
        namespace = {"fnmatch": fnmatch, "re": re}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        if not functions.issubset(namespace) or constant not in namespace:
            raise AssertionError("W1 matcher dependencies changed; review integration extraction")
        cls.match = staticmethod(namespace["_command_matches_terminal_allowlist"])
        cls.patterns = terminal_catalog()
        sys.stderr.write("W1 matcher source sha256=%s\n" % hashlib.sha256(source).hexdigest())

    def test_actual_w1_accepts_each_characterized_command(self):
        for command in ("aos help", "aos seat check --help", "aos seat check -"):
            with self.subTest(command=command):
                self.assertTrue(self.match(command, self.patterns))
                self.assertTrue(self.match(" " + command + "\n", self.patterns))

    def test_actual_w1_rejects_mutations_and_bare_regex_catalog(self):
        for command in ("aos help", "aos seat check --help", "aos seat check -"):
            with self.subTest(command=command):
                # Demonstrate the previous regex catalog's incompatibility.
                self.assertFalse(self.match(command, (r"\A" + command + r"\Z",)))
            for altered in mutation_variants(command):
                with self.subTest(command=altered):
                    self.assertFalse(self.match(altered, self.patterns))
        for command in ("aos sync", "touch x", "sh", "python3 -c 'pass'", "aos help extra"):
            with self.subTest(command=command):
                self.assertFalse(self.match(command, self.patterns))


if __name__ == "__main__":
    unittest.main()
