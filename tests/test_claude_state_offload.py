"""Contained offline fixtures: no production paths, mounts, or process inspection.

The script uses Python filesystem operations, so no rsync/stat/lsof/PID utilities
need to be invoked or faked. Subprocesses below are only our fixture invocations.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "claude" / "state-offload"
loader = importlib.machinery.SourceFileLoader("fixture_state_offload", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
offload = importlib.util.module_from_spec(spec)
# Compile the admitted script without writing bytecode beside the source.
exec(compile(loader.get_source(loader.name), str(SCRIPT), "exec"), offload.__dict__)
PAYLOAD = b"original\x00\xff\ntranscript bytes\r\n"


class Interrupted(BaseException):
    """Simulate process interruption without stopping or inspecting any process."""


class FakeWriter:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("wb")
        self.stopped = False

    def write(self, data):
        if self.stopped:
            raise RuntimeError("fixture writer already stopped")
        self.handle.write(data)
        self.handle.flush()

    def stop(self):
        self.handle.close()  # No retained open descriptor during cutover.
        self.stopped = True


def snapshot(root):
    """Record only the temporary fixture tree, without following symlinks."""
    result = {}
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(parent) / name
            key = str(path.relative_to(root))
            if path.is_symlink():
                result[key] = ("link", os.readlink(path))
            elif path.is_dir():
                result[key] = ("dir",)
            else:
                result[key] = ("file", path.read_bytes(), path.stat().st_mtime_ns)
    return result


class StateOffloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="state-offload-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.config = self.root / "config"
        self.state = self.root / "local-state"
        self.config.mkdir()
        self.tool = offload.Offload(self.config, self.state)
        self.env = {
            "HOME": str(self.root / "unused-home"),
            "USER": "fixture-only",
            "PATH": os.defpath,
            "CLAUDE_CONFIG_DIR": str(self.config),
            "CLAUDE_STATE_ROOT": str(self.state),
        }

    def seed(self, name="projects", data=PAYLOAD):
        writer = FakeWriter(self.config / name / "payload.bin")
        writer.write(data)
        writer.stop()
        self.assertTrue(writer.stopped)
        return writer

    def seed_all(self):
        for name in offload.DIRS:
            self.seed(name, PAYLOAD + name.encode())

    def run_tool(self, command, acknowledged=True, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.tool.run(command, acknowledged, dry_run)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def assert_original(self, parent, data=PAYLOAD):
        self.assertEqual((parent / "payload.bin").read_bytes(), data)

    def crash_migrate(self):
        real_link = offload.os.symlink

        def interrupt(target, source, *args, **kwargs):
            if Path(source) == self.config / "projects":
                raise Interrupted()
            return real_link(target, source, *args, **kwargs)

        with mock.patch.object(offload.os, "symlink", side_effect=interrupt):
            with self.assertRaises(Interrupted):
                self.run_tool("migrate")
        self.assertTrue(self.tool.journal.is_file())

    def test_cli_requires_acknowledgment_for_every_mutator(self):
        self.seed()
        before = snapshot(self.root)
        for command in ("migrate", "ensure", "revert"):
            with self.subTest(command=command):
                result = self.cli(command)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("--writers-stopped", result.stderr)
                self.assertEqual(snapshot(self.root), before)

    def test_help_documents_operator_not_automatic_quiescence(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = " ".join(result.stdout.split())
        for phrase in ("remote/shared-host", "open file descriptors", "not automatic",
                       "No process is inspected, stopped or killed", "--writers-stopped"):
            self.assertIn(phrase, text)
        self.assertNotIn("Safe with live sessions", text)
        self.assertNotIn("rsync --update", text)

    def test_byte_preserving_roundtrip_retains_all_originals(self):
        self.seed_all()
        (self.config / "projects" / "payload-link").symlink_to("payload.bin")
        self.run_tool("migrate")
        for name in offload.DIRS:
            source, destination, archive = self.tool.paths(name)
            expected = PAYLOAD + name.encode()
            self.assertEqual(os.readlink(source), str(destination))
            self.assert_original(destination, expected)
            self.assert_original(archive, expected)
        self.assertEqual(os.readlink(self.state / "projects" / "payload-link"), "payload.bin")
        self.run_tool("migrate")  # Canonical existing links are an idempotent no-op.
        current = b"new stopped-writer state\x00\xfe"
        writer = FakeWriter(self.state / "projects" / "payload.bin")
        writer.write(current)
        writer.stop()
        self.run_tool("revert")
        self.assertFalse((self.config / "projects").is_symlink())
        self.assert_original(self.config / "projects", current)
        self.assert_original(self.state / "projects", current)
        self.assert_original(self.tool.archive / "projects", PAYLOAD + b"projects")
        self.assertEqual(os.readlink(self.config / "projects" / "payload-link"), "payload.bin")
        self.run_tool("revert")  # Already-reverted directories are untouched.
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "collision"):
            self.run_tool("migrate")
        self.assertEqual(snapshot(self.root), before)

    def test_destination_newer_refused_without_merge_or_overwrite(self):
        self.seed()
        destination = self.state / "projects"
        destination.mkdir(parents=True)
        (destination / "payload.bin").write_bytes(b"newer original destination")
        os.utime(destination / "payload.bin", (2000000000, 2000000000))
        # Establish the cooperating lock before taking the immutable snapshot.
        with self.tool.locked():
            pass
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "destination collision"):
            self.run_tool("migrate")
        self.assertEqual(snapshot(self.root), before)
        self.assert_original(self.config / "projects")
        self.assert_original(destination, b"newer original destination")

    def test_late_directory_collision_is_preflighted_before_any_cutover(self):
        self.seed()
        self.tool.archive.mkdir()
        (self.tool.archive / "backups").mkdir()
        with self.assertRaisesRegex(offload.Refusal, "archive collision"):
            self.run_tool("migrate")
        self.assert_original(self.config / "projects")
        self.assertFalse(self.state.exists())
        self.assertFalse(self.tool.journal.exists())

    def test_staging_collision_is_never_reused(self):
        self.seed()
        collision = self.config / (offload.STAGE + "unexpected")
        collision.mkdir()
        (collision / "original").write_bytes(PAYLOAD)
        with self.assertRaisesRegex(offload.Refusal, "staging collision"):
            self.run_tool("migrate")
        self.assertEqual((collision / "original").read_bytes(), PAYLOAD)
        self.assert_original(self.config / "projects")
        self.assertFalse(self.state.exists())

    def test_foreign_links_rejected_by_all_mutators(self):
        foreign = self.root / "foreign-fixture"
        foreign.mkdir()
        (foreign / "payload.bin").write_bytes(PAYLOAD)
        (self.config / "projects").symlink_to(foreign, target_is_directory=True)
        for command in ("migrate", "ensure", "revert"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(offload.Refusal, "foreign link"):
                    self.run_tool(command)
                self.assertEqual(os.readlink(self.config / "projects"), str(foreign))
                self.assert_original(foreign)
                self.assertFalse(self.state.exists())

    def test_relative_link_even_to_managed_target_is_rejected(self):
        self.state.mkdir()
        (self.state / "projects").mkdir()
        (self.config / "projects").symlink_to("../local-state/projects")
        with self.assertRaisesRegex(offload.Refusal, "foreign link"):
            self.run_tool("ensure")

    def test_destination_symlink_is_not_followed(self):
        self.seed()
        self.state.mkdir()
        foreign = self.root / "foreign-fixture"
        foreign.mkdir()
        (foreign / "original").write_bytes(PAYLOAD)
        (self.state / "projects").symlink_to(foreign)
        with self.assertRaisesRegex(offload.Refusal, "foreign destination"):
            self.run_tool("migrate")
        self.assertEqual((foreign / "original").read_bytes(), PAYLOAD)
        self.assert_original(self.config / "projects")

    def test_archive_symlink_is_not_followed(self):
        self.seed()
        foreign = self.root / "foreign-fixture"
        foreign.mkdir()
        self.tool.archive.symlink_to(foreign)
        with self.assertRaisesRegex(offload.Refusal, "foreign archive root"):
            self.run_tool("migrate")
        self.assertEqual(list(foreign.iterdir()), [])
        self.assert_original(self.config / "projects")

    def test_overlapping_roots_are_refused_including_resolved_aliases(self):
        alias = self.root / "config-alias"
        alias.symlink_to(self.config)
        for destination in (self.config, self.config / "state", self.root,
                            alias / "nested-state"):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(offload.Refusal, "disjoint"):
                    offload.Offload(self.config, destination)
        self.assertEqual(list(self.config.iterdir()), [])

    def test_dry_run_and_status_are_inert_without_acknowledgment(self):
        self.seed_all()
        before = snapshot(self.root)
        result = self.cli("migrate", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run: migrate projects", result.stdout)
        self.assertEqual(snapshot(self.root), before)
        self.run_tool("migrate")
        linked = snapshot(self.root)
        for command in ("migrate", "ensure", "revert", "status"):
            result = self.cli(command, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(snapshot(self.root), linked)

    def test_link_failure_rolls_back_and_retains_copy_then_reruns(self):
        self.seed()
        real_link = offload.os.symlink

        def fail(target, source, *args, **kwargs):
            if Path(source) == self.config / "projects":
                raise OSError("injected link cutover failure")
            return real_link(target, source, *args, **kwargs)

        with mock.patch.object(offload.os, "symlink", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                self.run_tool("migrate")
        self.assert_original(self.config / "projects")
        self.assertFalse((self.tool.archive / "projects").exists())
        self.assertFalse((self.state / "projects").exists())
        self.assertFalse(self.tool.journal.exists())
        retained = list(self.state.glob(offload.RETAINED + "*"))
        self.assertEqual(len(retained), 1)
        self.assert_original(retained[0])
        self.run_tool("migrate")
        self.assert_original(self.state / "projects")
        self.assert_original(self.tool.archive / "projects")
        self.assert_original(retained[0])

    def test_partial_copy_failure_retains_partial_copy_not_lost_original(self):
        self.seed()

        def partial_copy(source, destination, **kwargs):
            (destination / "partial.bin").write_bytes(b"partial fixture copy")
            raise OSError("injected copy failure")

        with mock.patch.object(offload.shutil, "copytree", side_effect=partial_copy):
            with self.assertRaisesRegex(OSError, "copy failure"):
                self.run_tool("migrate")
        self.assert_original(self.config / "projects")
        self.assertFalse((self.state / "projects").exists())
        self.assertFalse(self.tool.journal.exists())
        retained = list(self.state.glob(offload.RETAINED + "*"))
        self.assertEqual(len(retained), 1)
        self.assertEqual((retained[0] / "partial.bin").read_bytes(), b"partial fixture copy")
        self.run_tool("migrate")
        self.assert_original(self.tool.archive / "projects")

    def test_revert_rename_failure_restores_original_link_and_local_state(self):
        self.seed()
        self.run_tool("migrate")
        real_rename = offload.os.rename

        def fail(source, destination):
            if Path(source).name.startswith(offload.STAGE) and \
                    Path(destination) == self.config / "projects":
                raise OSError("injected revert publish failure")
            return real_rename(source, destination)

        with mock.patch.object(offload.os, "rename", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                self.run_tool("revert")
        self.assertEqual(os.readlink(self.config / "projects"), str(self.state / "projects"))
        self.assert_original(self.state / "projects")
        self.assert_original(self.tool.archive / "projects")
        self.assertFalse(self.tool.journal.exists())
        retained = [path for path in self.config.glob(offload.RETAINED + "*") if path.is_dir()]
        self.assertEqual(len(retained), 1)
        self.assert_original(retained[0])
        self.run_tool("revert")
        self.assert_original(self.config / "projects")
        self.assert_original(self.state / "projects")

    def test_interruption_requires_ack_then_recovers_and_reruns(self):
        self.seed()
        self.crash_migrate()
        self.assertFalse((self.config / "projects").exists())
        self.assert_original(self.tool.archive / "projects")
        self.assert_original(self.state / "projects")
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "--writers-stopped"):
            self.run_tool("migrate", acknowledged=False)
        with self.assertRaisesRegex(offload.Refusal, "pending transaction"):
            self.run_tool("migrate", acknowledged=False, dry_run=True)
        self.assertEqual(snapshot(self.root), before)
        self.run_tool("migrate")
        self.assertFalse(self.tool.journal.exists())
        self.assertEqual(os.readlink(self.config / "projects"), str(self.state / "projects"))
        self.assert_original(self.tool.archive / "projects")
        retained = list(self.state.glob(offload.RETAINED + "*"))
        self.assertEqual(len(retained), 1)
        self.assert_original(retained[0])

    def test_interrupted_revert_recovers_parked_link_before_retry(self):
        self.seed()
        self.run_tool("migrate")
        real_rename = offload.os.rename

        def interrupt(source, destination):
            if Path(source).name.startswith(offload.STAGE) and \
                    Path(destination) == self.config / "projects":
                raise Interrupted()
            return real_rename(source, destination)

        with mock.patch.object(offload.os, "rename", side_effect=interrupt):
            with self.assertRaises(Interrupted):
                self.run_tool("revert")
        self.assertTrue(self.tool.journal.is_file())
        self.assertFalse((self.config / "projects").exists())
        self.assert_original(self.state / "projects")
        self.assert_original(self.tool.archive / "projects")
        self.run_tool("revert")
        self.assertFalse(self.tool.journal.exists())
        self.assert_original(self.config / "projects")
        self.assert_original(self.state / "projects")

    def test_interruption_after_link_publication_is_recoverable(self):
        self.seed()
        real_unlink = offload.Path.unlink

        def interrupt(path, *args, **kwargs):
            if path == self.tool.journal:
                raise Interrupted()
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(offload.Path, "unlink", new=interrupt):
            with self.assertRaises(Interrupted):
                self.run_tool("migrate")
        self.assertTrue(self.tool.journal.is_file())
        self.assertEqual(os.readlink(self.config / "projects"), str(self.state / "projects"))
        self.assert_original(self.tool.archive / "projects")
        self.run_tool("migrate")
        self.assertFalse(self.tool.journal.exists())
        self.assert_original(self.state / "projects")
        self.assert_original(self.tool.archive / "projects")

    def test_failed_rollback_keeps_journal_and_original_for_recovery(self):
        self.seed()
        real_rename = offload.os.rename
        real_link = offload.os.symlink

        def fail_link(target, source, *args, **kwargs):
            if Path(source) == self.config / "projects":
                raise OSError("injected cutover failure")
            return real_link(target, source, *args, **kwargs)

        def fail_restore(source, destination):
            if Path(source) == self.tool.archive / "projects" and \
                    Path(destination) == self.config / "projects":
                raise OSError("injected rollback failure")
            return real_rename(source, destination)

        with mock.patch.object(offload.os, "symlink", side_effect=fail_link), \
                mock.patch.object(offload.os, "rename", side_effect=fail_restore):
            with self.assertRaisesRegex(OSError, "cutover"):
                self.run_tool("migrate")
        self.assertTrue(self.tool.journal.is_file())
        self.assert_original(self.tool.archive / "projects")
        self.assertFalse((self.state / "projects").exists())
        retained = list(self.state.glob(offload.RETAINED + "*"))
        self.assertEqual(len(retained), 1)
        self.assert_original(retained[0])
        self.run_tool("migrate")
        self.assertFalse(self.tool.journal.exists())
        self.assert_original(self.tool.archive / "projects")
        self.assert_original(self.state / "projects")
        self.assert_original(retained[0])

    def test_ambiguous_original_archive_recovery_refuses_both_untouched(self):
        self.seed()
        self.crash_migrate()
        (self.config / "projects").mkdir()
        (self.config / "projects" / "foreign-original").write_bytes(b"another original")
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "ambiguous original/archive"):
            self.run_tool("migrate")
        self.assertEqual(snapshot(self.root), before)
        self.assert_original(self.tool.archive / "projects")
        self.assertTrue(self.tool.journal.exists())

    def test_ambiguous_stage_and_destination_refuse_without_discarding_either(self):
        self.seed()
        self.crash_migrate()
        record = json.loads(self.tool.journal.read_text())
        stage, _, _ = self.tool.record_paths(record)
        stage.mkdir()
        (stage / "another-original").write_bytes(b"unexpected fixture copy")
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "ambiguous staging/destination"):
            self.run_tool("migrate")
        self.assertEqual(snapshot(self.root), before)
        self.assert_original(self.tool.archive / "projects")
        self.assert_original(self.state / "projects")

    def test_invalid_journal_and_mismatched_roots_never_guess_recovery(self):
        self.seed()
        self.crash_migrate()
        record = json.loads(self.tool.journal.read_text())
        record["state"] = str(self.root / "different-fixture-root")
        self.tool.journal.write_text(json.dumps(record))
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "roots differ"):
            self.run_tool("migrate")
        self.assertEqual(snapshot(self.root), before)
        self.tool.journal.write_text("{incomplete")
        before = snapshot(self.root)
        with self.assertRaisesRegex(offload.Refusal, "ambiguous transaction"):
            self.run_tool("migrate")
        self.assertEqual(snapshot(self.root), before)

    def test_ensure_seeds_only_canonical_targets_from_retained_archives(self):
        self.seed_all()
        self.run_tool("migrate")
        previous_host = self.root / "previous-host-fixture-state"
        self.state.rename(previous_host)
        before = snapshot(self.root)
        result = self.cli("ensure", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run: ensure projects", result.stdout)
        self.assertEqual(snapshot(self.root), before)
        self.run_tool("ensure")
        for name in offload.DIRS:
            expected = PAYLOAD + name.encode()
            self.assert_original(self.state / name, expected)
            self.assert_original(self.tool.archive / name, expected)
            self.assert_original(previous_host / name, expected)
            self.assertEqual(os.readlink(self.config / name), str(self.state / name))
        before = snapshot(self.root)
        self.run_tool("ensure")
        self.assertEqual(snapshot(self.root), before)

    def test_ensure_copy_publish_failure_is_recoverable(self):
        self.seed_all()
        self.run_tool("migrate")
        self.state.rename(self.root / "previous-host-fixture-state")
        real_rename = offload.os.rename

        def fail(source, destination):
            if Path(source).name.startswith(offload.STAGE) and \
                    Path(destination) == self.state / "projects":
                raise OSError("injected ensure publish failure")
            return real_rename(source, destination)

        with mock.patch.object(offload.os, "rename", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                self.run_tool("ensure")
        self.assertTrue((self.config / "projects").is_symlink())
        self.assertFalse((self.state / "projects").exists())
        self.assert_original(self.tool.archive / "projects", PAYLOAD + b"projects")
        self.assertFalse(self.tool.journal.exists())
        retained = list(self.state.glob(offload.RETAINED + "*"))
        self.assertEqual(len(retained), 1)
        self.assert_original(retained[0], PAYLOAD + b"projects")
        self.run_tool("ensure")
        self.assert_original(self.state / "projects", PAYLOAD + b"projects")

    def test_dangling_without_seed_refuses_instead_of_inventing_empty_state(self):
        (self.config / "projects").symlink_to(self.state / "projects")
        with self.assertRaisesRegex(offload.Refusal, "no archived seed"):
            self.run_tool("ensure")
        with self.assertRaisesRegex(offload.Refusal, "cannot revert dangling"):
            self.run_tool("revert")
        self.assertFalse(self.state.exists())

    def test_deterministic_competing_fixture_invocations(self):
        self.seed()
        # The first *fixture* invocation pauses inside its first transaction,
        # after acquiring the real advisory lock. No PID/lsof/host inspection,
        # sleeps, or timing-based inference is used to establish contention.
        worker = r'''
import runpy
import sys
module = runpy.run_path(sys.argv[1], run_name="contained_fixture")
cls = module["Offload"]
original = cls.transact
first = True
def paused(self, *args):
    global first
    if first:
        first = False
        print("fixture-lock-held", flush=True)
        if sys.stdin.buffer.read(1) != b"R":
            raise RuntimeError("fixture release missing")
    return original(self, *args)
cls.transact = paused
sys.exit(module["main"](["migrate", "--writers-stopped"]))
'''
        holder = subprocess.Popen([sys.executable, "-c", worker, str(SCRIPT)],
                                  env=self.env, cwd=self.root, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as ready:
                ready.register(holder.stdout, selectors.EVENT_READ)
                self.assertTrue(ready.select(timeout=10), "fixture did not acquire lock")
            self.assertEqual(holder.stdout.readline().strip(), "fixture-lock-held")
            loser = self.cli("migrate", "--writers-stopped")
            self.assertEqual(loser.returncode, 1, loser.stderr)
            self.assertIn("another state-offload invocation holds the lock", loser.stderr)
            self.assert_original(self.config / "projects")
            self.assertFalse(self.tool.journal.exists())
            self.assertFalse((self.state / "projects").exists())
            # A different config root sharing this state root must also lose;
            # a config-only lock would allow a destructive destination race.
            other_config = self.root / "other-config-fixture"
            writer = FakeWriter(other_config / "projects" / "payload.bin")
            writer.write(b"other original")
            writer.stop()
            other_env = dict(self.env)
            other_env["CLAUDE_CONFIG_DIR"] = str(other_config)
            other_loser = subprocess.run(
                [sys.executable, str(SCRIPT), "migrate", "--writers-stopped"],
                env=other_env, cwd=self.root, capture_output=True, text=True, timeout=10)
            self.assertEqual(other_loser.returncode, 1, other_loser.stderr)
            self.assertIn("holds the lock", other_loser.stderr)
            self.assert_original(other_config / "projects", b"other original")
            self.assertFalse((other_config / offload.JOURNAL).exists())
            holder.stdin.write("R")
            holder.stdin.flush()
            stdout, stderr = holder.communicate(timeout=10)
            self.assertEqual(holder.returncode, 0, stdout + stderr)
        finally:
            # Cleanup is restricted to the subprocess created by this fixture.
            if holder.poll() is None:
                holder.kill()
                holder.communicate(timeout=10)
            for pipe in (holder.stdin, holder.stdout, holder.stderr):
                pipe.close()
        self.assert_original(self.state / "projects")
        self.assert_original(self.tool.archive / "projects")
        result = self.cli("migrate", "--writers-stopped")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.tool.journal.exists())


if __name__ == "__main__":
    unittest.main()
