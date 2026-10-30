"""Tests for bin/cred/cred and its credential-sync backend routing.

Contract under test:
  - status/doctor never print token material
  - diverged codex grants fail codex.grant; doctor --fix aligns them
  - leaked CODEX_* vars in the global tmux env are detected
  - backends route only when their declared domain matches the host domain
  - credential-sync uses an eligible backend, else falls through to legacy
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRED = ROOT / "bin" / "cred" / "cred"
SYNC = ROOT / "bin" / "credential-sync"


def jwt(claims: dict) -> str:
    def seg(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'none'})}.{seg(claims)}.sig"


BACKEND = """#!/usr/bin/env bash
case "$1" in
  describe) echo '{"schema":"cred-backend.v1","name":"fake","domain":"%s","providers":["openai-codex"]}' ;;
  materialize) echo "materialized $*" > "%s"; exit 0 ;;
esac
"""


class CredTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        (self.home / ".codex").mkdir(parents=True)
        (self.home / ".pi" / "agent").mkdir(parents=True)
        (self.home / ".hermes").mkdir(parents=True)
        self.conf = self.tmp / "conf"
        (self.conf / "backends.d").mkdir(parents=True)
        self.env = {
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin",
            "CRED_CONFIG_DIR": str(self.conf),
            "CODEX_GRANT_LOCK": str(self.tmp / "lock"),
        }
        exp = int(time.time()) + 86400
        self.access = jwt({"exp": exp})
        self.id_token = jwt({"email": "me@example.org", "https://api.openai.com/auth": {"chatgpt_plan_type": "pro", "chatgpt_account_id": "acct-123456"}})

    def write_stores(self, cli_refresh: str, pi_refresh: str) -> None:
        (self.home / ".codex" / "auth.json").write_text(json.dumps({
            "auth_mode": "chatgpt",
            "tokens": {"id_token": self.id_token, "access_token": self.access, "refresh_token": cli_refresh, "account_id": "a"},
            "last_refresh": "2026-10-29T00:00:00Z",
        }))
        (self.home / ".pi" / "agent" / "auth.json").write_text(json.dumps({
            "openai-codex": {"type": "oauth", "access": self.access, "refresh": pi_refresh, "expires": 1000},
        }))

    def cred(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(CRED), *args], capture_output=True, text=True, env=self.env, timeout=60)

    def rows(self, proc: subprocess.CompletedProcess[str]) -> dict:
        return {r["check"]: r for r in json.loads(proc.stdout)["checks"]}

    def test_diverged_grants_fail_and_doctor_fix_aligns(self) -> None:
        self.write_stores("refresh-NEW-secret", "refresh-OLD-secret")
        proc = self.cred("status", "--json", "--only", "codex")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.rows(proc)["codex.grant"]["status"], "fail")
        self.assertNotIn("secret", proc.stdout + proc.stderr)
        self.assertNotIn(self.access, proc.stdout)

        fixed = self.cred("doctor", "--fix", "--json", "--only", "codex")
        self.assertEqual(fixed.returncode, 0, fixed.stderr)
        self.assertEqual(self.rows(fixed)["codex.grant"]["status"], "ok")
        pi = json.loads((self.home / ".pi" / "agent" / "auth.json").read_text())
        self.assertEqual(pi["openai-codex"]["refresh"], "refresh-NEW-secret")

    def test_account_is_reduced_to_domain_and_suffix(self) -> None:
        self.write_stores("r", "r")
        detail = self.rows(self.cred("status", "--json", "--only", "codex"))["codex.account"]["detail"]
        self.assertIn("domain=example.org", detail)
        self.assertIn("acct=…123456", detail)
        self.assertNotIn("me@", detail)

    def test_work_account_on_personal_host_fails(self) -> None:
        self.write_stores("r", "r")
        (self.conf / "host").write_text("domain=personal\nwork_email_domains=example.org\n")
        self.assertEqual(self.rows(self.cred("status", "--json", "--only", "codex"))["codex.account"]["status"], "fail")

    def add_backend(self, domain: str) -> Path:
        marker = self.tmp / "materialized"
        path = self.conf / "backends.d" / "fake"
        path.write_text(BACKEND % (domain, marker))
        path.chmod(0o755)
        return marker

    def test_backend_domain_mismatch_is_not_routed(self) -> None:
        (self.conf / "host").write_text("domain=personal\n")
        marker = self.add_backend("work")
        self.assertEqual(self.cred("materialize", "--provider", "openai-codex", "--targets", "pi", "--apply").returncode, 3)
        self.assertFalse(marker.exists())
        self.assertEqual(self.rows(self.cred("status", "--json", "--only", "backends"))["backend.fake"]["status"], "fail")

    def test_credential_sync_routes_to_matching_backend(self) -> None:
        (self.conf / "host").write_text("domain=personal\n")
        marker = self.add_backend("personal")
        proc = subprocess.run(["bash", str(SYNC), "--provider", "openai-codex"], capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["path"], "backend")
        self.assertIn("--targets codex-cli,hermes,pi --apply", marker.read_text())

    def test_credential_sync_falls_back_to_legacy_without_backend(self) -> None:
        self.write_stores("r1", "r2")
        proc = subprocess.run(["bash", str(SYNC), "--provider", "openai-codex"], capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["path"], "legacy")


class TmuxLeakTest(unittest.TestCase):
    def test_leak_detected(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        fake = tmp / "tmux"
        fake.write_text("#!/bin/sh\necho CODEX_SANDBOX_NETWORK_DISABLED=1\necho CODEX_HOME=/x\necho EDITOR=nvim\n")
        fake.chmod(0o755)
        env = {"HOME": str(tmp), "PATH": f"{tmp}:/usr/bin:/bin", "CRED_CONFIG_DIR": str(tmp / "c")}
        proc = subprocess.run(["python3", str(CRED), "status", "--json", "--only", "env"], capture_output=True, text=True, env=env, timeout=30)
        row = json.loads(proc.stdout)["checks"][0]
        self.assertEqual(row["status"], "fail")
        self.assertIn("1 agent-session vars", row["detail"])


if __name__ == "__main__":
    unittest.main()
