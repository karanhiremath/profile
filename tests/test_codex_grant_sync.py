from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin/hermes/codex_grant_sync.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_grant_sync", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_module()


class CodexGrantSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.hermes = root / "hermes"
        self.codex = root / "codex"
        self.pi = root / "pi"
        for path in (self.hermes, self.codex, self.pi):
            path.mkdir()
        self.env = {
            "HERMES_HOME": str(self.hermes),
            "CODEX_HOME": str(self.codex),
            "PI_CODING_AGENT_DIR": str(self.pi),
            "CODEX_GRANT_LOCK": str(root / "grant.lock"),
        }
        self._old = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        os.environ.pop("HERMES_CODEX_GRANT_ISOLATE", None)

    def tearDown(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.environ.pop("HERMES_CODEX_GRANT_ISOLATE", None)
        self.tmp.cleanup()

    def _write_hermes(self, access: str, refresh: str, last: str = "2026-09-11T20:00:00Z"):
        (self.hermes / "auth.json").write_text(json.dumps({
            "version": 1,
            "providers": {
                "openai-codex": {
                    "tokens": {"access_token": access, "refresh_token": refresh},
                    "last_refresh": last,
                    "auth_mode": "chatgpt",
                }
            },
            "credential_pool": {
                "openai-codex": [
                    {
                        "source": "device_code",
                        "access_token": access,
                        "refresh_token": refresh,
                    }
                ]
            },
        }))

    def _write_cli(self, access: str, refresh: str, last: str = "2026-09-01T00:00:00Z"):
        (self.codex / "auth.json").write_text(json.dumps({
            "auth_mode": "chatgpt",
            "tokens": {"access_token": access, "refresh_token": refresh},
            "last_refresh": last,
        }))

    def _write_pi(self, access: str, refresh: str, expires: int = 2_000_000_000_000):
        (self.pi / "auth.json").write_text(json.dumps({
            "anthropic": {"type": "api_key", "key": "keep-me"},
            "openai-codex": {
                "type": "oauth",
                "access": access,
                "refresh": refresh,
                "expires": expires,
            },
        }))

    def test_adopt_picks_newest_and_write_throughs(self):
        self._write_hermes("hermes-access", "stale-refresh", "2026-09-10T00:00:00Z")
        self._write_cli("cli-access", "older-refresh", "2026-09-01T00:00:00Z")
        self._write_pi("pi-access", "fresh-refresh", expires=2_100_000_000_000)

        result = sync.adopt_newest()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "pi")
        hermes = json.loads((self.hermes / "auth.json").read_text())
        cli = json.loads((self.codex / "auth.json").read_text())
        pi = json.loads((self.pi / "auth.json").read_text())
        self.assertEqual(hermes["providers"]["openai-codex"]["tokens"]["refresh_token"], "fresh-refresh")
        self.assertEqual(cli["tokens"]["refresh_token"], "fresh-refresh")
        self.assertEqual(pi["openai-codex"]["refresh"], "fresh-refresh")
        self.assertEqual(pi["anthropic"]["key"], "keep-me")
        self.assertEqual(
            hermes["credential_pool"]["openai-codex"][0]["refresh_token"],
            "fresh-refresh",
        )
        self.assertTrue(result["refresh_aligned"])

    def test_isolate_skips_peer_export(self):
        os.environ["HERMES_CODEX_GRANT_ISOLATE"] = "1"
        self._write_hermes("hermes-access", "hermes-refresh")
        result = sync.adopt_newest()
        self.assertEqual(result["wrote"], [])
        self.assertFalse((self.codex / "auth.json").exists())
        self.assertFalse((self.pi / "auth.json").exists())

    def test_adopt_if_peer_newer_skips_matching_refresh(self):
        self._write_hermes("a", "same-refresh", "2026-09-11T22:00:00Z")
        self._write_cli("b", "same-refresh", "2026-09-11T21:00:00Z")
        self._write_pi("c", "same-refresh")
        adopted = sync.adopt_if_peer_newer({"access_token": "a", "refresh_token": "same-refresh"})
        self.assertIsNone(adopted)

    def test_status_never_emits_token_values(self):
        self._write_hermes("secret-access-value", "secret-refresh-value")
        self._write_pi("secret-access-value", "secret-refresh-value")
        report = sync.status_report()
        blob = json.dumps(report)
        self.assertNotIn("secret-access-value", blob)
        self.assertNotIn("secret-refresh-value", blob)
        self.assertTrue(report["hermes_refresh_matches_pi"])

    def test_hermes_wrapper_exports_on_save(self):
        self._write_cli("old-cli", "old-refresh")
        saved = {}

        def fake_save(tokens, last_refresh=None, label=None):
            saved.update(tokens)

        auth = SimpleNamespace(
            _save_codex_tokens=fake_save,
            _refresh_codex_auth_tokens=lambda tokens, timeout: tokens,
            _recover_codex_tokens_from_cli=lambda reason: None,
            CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS=120,
        )
        sync.install_into_hermes_auth(auth)
        auth._save_codex_tokens(
            {"access_token": "new-access", "refresh_token": "new-refresh"},
            last_refresh="2026-09-11T23:00:00Z",
        )
        self.assertEqual(saved["refresh_token"], "new-refresh")
        cli = json.loads((self.codex / "auth.json").read_text())
        pi = json.loads((self.pi / "auth.json").read_text())
        self.assertEqual(cli["tokens"]["refresh_token"], "new-refresh")
        self.assertEqual(pi["openai-codex"]["refresh"], "new-refresh")


if __name__ == "__main__":
    unittest.main()
