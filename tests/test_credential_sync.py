"""Tests for the generic credential-sync dispatcher (profile/bin/credential-sync).

Contract under test (P0 CLI pipeline contract):
  - stdout is always a single-line JSON payload, never credential material
  - diagnostics go to stderr only
  - unknown/missing provider -> structured no-op (exit 0), never a guess
  - provider registered -> legacy dispatch, exit 0 on success, 1 on failure
  - usage errors -> exit 2 with empty stdout
  - symlinked invocation resolves script dir (launchers may PATH or symlink it)
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "bin" / "credential-sync"

FAKE_OK = """#!/usr/bin/env python3
print("cli_refresh_len=211 cli_present=true")  # lengths/booleans only
"""
FAKE_FAIL = """#!/usr/bin/env python3
raise SystemExit(1)
"""


def run_shim(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("CREDENTIAL_SYNC_LEGACY_DIR", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SHIM), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one stdout line, got {lines!r}"
    return json.loads(lines[0])


class CredentialSyncTests(unittest.TestCase):
    def test_missing_provider_is_structured_noop(self) -> None:
        p = run_shim()
        self.assertEqual(p.returncode, 0)
        body = payload(p)
        self.assertEqual(body["schema"], "credential-sync.v1")
        self.assertEqual(body["status"], "noop")
        self.assertEqual(body["reason"], "missing-provider")

    def test_unregistered_provider_is_structured_noop(self) -> None:
        # Genericity guarantee: providers without registry entries must never
        # break a launcher and must never guess an implementation.
        p = run_shim("--provider", "anthropic", "--seat", "s1")
        self.assertEqual(p.returncode, 0)
        body = payload(p)
        self.assertEqual(body["status"], "noop")
        self.assertEqual(body["reason"], "provider-not-registered")
        self.assertEqual(body["provider"], "anthropic")
        self.assertEqual(body["seat"], "s1")

    def test_usage_error_empty_stdout(self) -> None:
        p = run_shim("--bogus")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "")
        self.assertIn("unknown argument", p.stderr)

    def test_help_empty_stdout_payload_free(self) -> None:
        p = run_shim("--help")
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("{", p.stdout)

    def test_registered_provider_legacy_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            legacy = Path(td) / "hermes"
            legacy.mkdir()
            (legacy / "codex_grant_sync.py").write_text(FAKE_OK)
            p = run_shim("--provider", "openai-codex", env_extra={"CREDENTIAL_SYNC_LEGACY_DIR": str(legacy)})
            self.assertEqual(p.returncode, 0, p.stderr)
            body = payload(p)
            self.assertEqual(body["status"], "ok")
            self.assertEqual(body["path"], "legacy")
            # Raw legacy stdout (lengths/booleans) must never be re-emitted.
            self.assertNotIn("cli_refresh_len", p.stdout)

    def test_registered_provider_legacy_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            legacy = Path(td) / "hermes"
            legacy.mkdir()
            (legacy / "codex_grant_sync.py").write_text(FAKE_FAIL)
            p = run_shim("--provider", "codex", env_extra={"CREDENTIAL_SYNC_LEGACY_DIR": str(legacy)})
            self.assertEqual(p.returncode, 1)
            body = payload(p)
            self.assertEqual(body["status"], "fail")
            self.assertEqual(body["reason"], "adopt-failed")

    def test_registered_provider_missing_impl_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = run_shim("--provider", "openai-codex", env_extra={"CREDENTIAL_SYNC_LEGACY_DIR": td})
            self.assertEqual(p.returncode, 1)
            body = payload(p)
            self.assertEqual(body["status"], "fail")
            self.assertTrue(body["reason"].startswith("legacy-impl-missing"))

    def test_symlinked_invocation_resolves_script_dir(self) -> None:
        # Launchers/symlink (~/.local/bin) must resolve to the real tree, so the
        # default legacy dir sits next to the real shim, not next to the link.
        with tempfile.TemporaryDirectory() as td:
            linkbin = Path(td) / "bin"
            linkbin.mkdir()
            link = linkbin / "credential-sync"
            link.symlink_to(SHIM)
            legacy = linkbin / "hermes"  # wrong dir if resolution fails
            legacy.mkdir()
            (legacy / "codex_grant_sync.py").write_text(FAKE_FAIL)
            env = os.environ.copy()
            env.pop("CREDENTIAL_SYNC_LEGACY_DIR", None)
            p = subprocess.run(
                ["bash", str(link), "--provider", "openai-codex"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            body = payload(p)
            # Sentinel semantics: link dir holds a FAILING fake impl. Broken
            # resolution would run the fake -> status=fail/adopt-failed. Correct
            # resolution runs the real codex_grant_sync.py -> status=ok
            # (idempotent adopt on live single-writer stores; aligned stores
            # mean no-op writes).
            self.assertEqual(body["path"], "legacy", body)
            self.assertEqual(body["status"], "ok", body)

    def test_stdout_is_never_multi_line_json_or_secret_material(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            legacy = Path(td) / "hermes"
            legacy.mkdir()
            (legacy / "codex_grant_sync.py").write_text(FAKE_OK)
            p = run_shim("--provider", "openai-codex", env_extra={"CREDENTIAL_SYNC_LEGACY_DIR": str(legacy)})
            self.assertEqual(len(p.stdout.strip().splitlines()), 1)
            self.assertNotIn("sk-ant", p.stdout + p.stderr)
            self.assertNotIn("refresh_token", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()