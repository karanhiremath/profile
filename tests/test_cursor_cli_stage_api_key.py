from __future__ import annotations

import importlib.machinery
import importlib.util
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "cursor-cli" / "stage-api-key"


def load_module():
    loader = importlib.machinery.SourceFileLoader("cursor_stage_api_key", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


stage_api_key = load_module()


class CursorStageApiKeyTests(unittest.TestCase):
    def test_default_dry_run_uses_sandbox_target_and_does_not_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp) / "sandbox"
            called = False

            def resolver(ref):
                nonlocal called
                called = True
                raise AssertionError("dry-run must not resolve secrets")

            out = io.StringIO()
            rc = stage_api_key.main(
                [],
                env={"AGENT_SANDBOX_ROOT": str(sandbox), "HOME": str(Path(tmp) / "home")},
                resolver=resolver,
                stdout=out,
                stderr=io.StringIO(),
            )

            self.assertEqual(rc, 0)
            self.assertFalse(called)
            self.assertIn(f"would_update[cursor]={sandbox / 'state' / 'cursor' / 'agent.env'}", out.getvalue())
            self.assertFalse(sandbox.exists())

    def test_default_op_ref_is_passed_to_injected_resolver(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs = []

            def resolver(ref):
                refs.append(ref)
                return "secret-value"

            rc = stage_api_key.main(
                ["--write", "--target-dir", tmp],
                env={"HOME": str(Path(tmp) / "home")},
                resolver=resolver,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

            self.assertEqual(rc, 0)
            self.assertEqual(refs, ["op://Personal/Cursor pi-coding-agent/credential"])

    def test_write_preserves_other_env_vars_and_updates_only_cursor_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cursor" / "agent.env"
            target.parent.mkdir()
            target.write_text(
                "# keep comments\n"
                "export OTHER_VAR='keep'\n"
                "CURSOR_API_KEY=old\n"
                "CURSOR_API_KEY_EXTRA=untouched\n",
                encoding="utf-8",
            )

            out = io.StringIO()
            rc = stage_api_key.main(
                ["--write", "--target-file", str(target)],
                env={"HOME": str(Path(tmp) / "home")},
                resolver=lambda ref: "new ' key",
                stdout=out,
                stderr=io.StringIO(),
            )

            self.assertEqual(rc, 0)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "# keep comments\n"
                "export OTHER_VAR='keep'\n"
                "CURSOR_API_KEY='new '\"'\"' key'\n"
                "CURSOR_API_KEY_EXTRA=untouched\n",
            )
            self.assertNotIn("new", out.getvalue())

    def test_write_creates_private_parent_and_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "private" / "agent.env"

            rc = stage_api_key.main(
                ["--write", "--target-file", str(target)],
                env={"HOME": str(Path(tmp) / "home")},
                resolver=lambda ref: "secret-value",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

            self.assertEqual(rc, 0)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(target.read_text(encoding="utf-8"), "CURSOR_API_KEY=secret-value\n")

    def test_relative_target_file_can_be_rooted_in_target_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = stage_api_key.main(
                ["--write", "--target-dir", tmp, "--target-file", "nested.env"],
                env={"HOME": str(Path(tmp) / "home")},
                resolver=lambda ref: "abc123",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmp) / "nested.env").exists())

    def test_default_resolver_uses_injected_subprocess_runner(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, 0, stdout=" resolved-secret\n", stderr="")

        value = stage_api_key.default_resolver("op://Personal/Test/key", runner=fake_run)

        self.assertEqual(value, " resolved-secret")
        self.assertEqual(calls[0][0], ["op", "read", "op://Personal/Test/key"])
        self.assertFalse(calls[0][1]["check"])


if __name__ == "__main__":
    unittest.main()
