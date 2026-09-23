"""Unit tests for bin/hermes/state_doctor.py (hermes.state-doctor.v1)."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin/hermes/state_doctor.py"

spec = importlib.util.spec_from_file_location("state_doctor_unit", SCRIPT)
assert spec and spec.loader
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)


def make_store(tmp: Path, journal_mode: str = "delete", sessions: int = 2) -> None:
    conn = sqlite3.connect(str(tmp / "state.db"))
    conn.execute("PRAGMA journal_mode=" + journal_mode)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, message_count INT)")
    for i in range(sessions):
        conn.execute("INSERT INTO sessions VALUES (?, ?)", (f"s{i}", i + 1))
    conn.commit()
    conn.close()


class StateDoctorCase(unittest.TestCase):
    """Isolates HERMES_AGENTS_DATA_HOME so tests never touch the real store.

    profile() creates <tmp>/<name>/profiles/<name> (nested layout) and
    returns that runtime home; tests then census profile name 'lane'.
    """
    PROFILE = "any"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_data_home = os.environ.get("HERMES_AGENTS_DATA_HOME")
        os.environ["HERMES_AGENTS_DATA_HOME"] = self.tmp.name
        self.home = Path(self.tmp.name) / self.PROFILE / "profiles" / self.PROFILE
        self.home.mkdir(parents=True)

    def tearDown(self) -> None:
        if self._old_data_home is None:
            os.environ.pop("HERMES_AGENTS_DATA_HOME", None)
        else:
            os.environ["HERMES_AGENTS_DATA_HOME"] = self._old_data_home
        self.tmp.cleanup()

    def result(self) -> dict:
        return sd.census_profile(self.PROFILE)


class PathsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("HERMES_AGENTS_DATA_HOME")
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HERMES_AGENTS_DATA_HOME"] = self.tmp.name

    def tearDown(self) -> None:
        del os.environ["HERMES_AGENTS_DATA_HOME"]
        self.tmp.cleanup()

    def test_runtime_home_nested_layout(self) -> None:
        nested = Path(self.tmp.name) / "p1" / "profiles" / "p1"
        nested.mkdir(parents=True)
        self.assertEqual(sd.runtime_home("p1"), nested)

    def test_runtime_home_flat_layout(self) -> None:
        flat = Path(self.tmp.name) / "p2"
        flat.mkdir()
        self.assertEqual(sd.runtime_home("p2"), flat)


class HeaderTest(unittest.TestCase):
    def test_wal_header_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            make_store(Path(tmp), journal_mode="wal")
            store = sd.classify_store(Path(tmp))
            self.assertEqual(store["journal_mode"], "wal")

    def test_delete_header_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            make_store(Path(tmp), journal_mode="delete")
            store = sd.classify_store(Path(tmp))
            self.assertEqual(store["status"], "ok")
            self.assertEqual(store["journal_mode"], "delete")

    def test_missing_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = sd.classify_store(Path(tmp))
            self.assertEqual(store["status"], "missing")

    def test_garbage_header_is_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "state.db").write_bytes(b"\xde\xad" * 32)
            store = sd.classify_store(Path(tmp))
            self.assertEqual(store["status"], "malformed")

    def test_truncated_sqlite_is_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "state.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 4)
            store = sd.classify_store(Path(tmp))
            self.assertEqual(store["status"], "malformed")


class CensusTest(StateDoctorCase):
    def test_healthy_local_store_passes(self) -> None:
        make_store(self.home)
        result = self.result()
        self.assertTrue(result["ok"], json.dumps(result, indent=2))
        ids = {c["id"]: c["status"] for c in result["checks"]}
        self.assertEqual(ids["store.integrity"], "pass")

    def test_wal_store_on_nfs_fails(self) -> None:
        make_store(self.home, journal_mode="wal")
        with unittest.mock.patch.object(sd, "fs_type_of", return_value="nfs"):
            result = self.result()
        self.assertFalse(result["ok"])
        self.assertIn("journal.nfs-wal", result["failed_checks"])

    def test_wal_on_local_fs_passes(self) -> None:
        make_store(self.home, journal_mode="wal")
        with unittest.mock.patch.object(sd, "fs_type_of", return_value="ext2/ext3/ext4"):
            result = self.result()
        self.assertNotIn("journal.nfs-wal", result["failed_checks"])

    def test_corrupt_store_fails(self) -> None:
        (self.home / "state.db").write_bytes(b"SQLite format 3\x00" + b"\xff" * 400)
        result = self.result()
        self.assertFalse(result["ok"])
        self.assertIn("store.integrity", result["failed_checks"])

    def test_long_home_fails_afunix_check(self) -> None:
        make_store(self.home)
        deep = self.home / ("deep-" * 20)
        deep.mkdir()
        with unittest.mock.patch.object(sd, "runtime_home", return_value=deep):
            result = self.result()
        self.assertFalse(result["ok"])
        self.assertIn("afunix.path-length", result["failed_checks"])

    def test_multiple_writers_fail(self) -> None:
        make_store(self.home)
        fake = [{"pid": 100, "role": "gateway", "cmdline": "x"},
                {"pid": 101, "role": "tui_gateway", "cmdline": "x"}]
        with unittest.mock.patch.object(sd, "live_writer_pids", return_value=fake):
            result = self.result()
        self.assertFalse(result["ok"])
        self.assertIn("writers.single", result["failed_checks"])

    def test_stale_holder_warns_not_fails(self) -> None:
        make_store(self.home)
        (self.home / ".gateway.lock.holder").write_text(
            "host=old-host\npid=999999999\nstarted=2026-09-15\n")
        result = self.result()
        self.assertTrue(result["ok"], json.dumps(result, indent=2))
        ids = {c["id"]: c["status"] for c in result["checks"]}
        self.assertEqual(ids["flock.holder"], "warn")


class RepairTest(StateDoctorCase):
    def test_repair_refuses_healthy_store(self) -> None:
        make_store(self.home, journal_mode="delete")
        result = sd.repair_profile(self.PROFILE, confirm=True, salvage=False)
        self.assertEqual(result["refused"], (
            "store is healthy and journal mode is not WAL; nothing to repair"))

    def test_repair_refuses_without_confirm_when_writers(self) -> None:
        make_store(self.home, journal_mode="wal")
        fake = [{"pid": os.getpid() + 999999, "role": "gateway", "cmdline": "x"}]
        with unittest.mock.patch.object(sd, "live_writer_pids", return_value=fake):
            result = sd.repair_profile(self.PROFILE, confirm=False, salvage=False)
        self.assertTrue(result["refused"])

    def test_repair_quarantines_and_creates_fresh_store(self) -> None:
        make_store(self.home, journal_mode="wal")  # WAL without writers = repairable drift
        result = sd.repair_profile(self.PROFILE, confirm=True, salvage=False)
        self.assertTrue(result["ok"], json.dumps(result, indent=2))
        quarantined = list(self.home.glob("state.db.malformed-*"))
        self.assertTrue(quarantined, "quarantine copy must exist")
        self.assertEqual(result["post"]["status"], "ok")
        self.assertEqual(result["post"]["journal_mode"], "delete")
        conn = sqlite3.connect(str(self.home / "state.db"))
        self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0], "ok")
        conn.close()

    def test_repair_of_corrupt_store(self) -> None:
        (self.home / "state.db").write_bytes(b"\xde\xad" * 32)
        result = sd.repair_profile(self.PROFILE, confirm=True, salvage=False)
        self.assertTrue(result["ok"])
        self.assertTrue(list(self.home.glob("state.db.malformed-*")))

    def test_cli_repair_requires_yes(self) -> None:
        make_store(self.home, journal_mode="wal")
        os.environ["HERMES_AGENTS_DATA_HOME"] = self.tmp.name
        try:
            code = sd.main(["repair", "--profile", self.PROFILE])
        finally:
            os.environ.pop("HERMES_AGENTS_DATA_HOME", None)
        self.assertEqual(code, 2)


class CliContractTest(unittest.TestCase):
    def test_stdout_is_json_stderr_quiet_on_preflight(self) -> None:
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            make_store(home)
            out, err = io.StringIO(), io.StringIO()
            os.environ["HERMES_AGENTS_DATA_HOME"] = tmp
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = sd.main(["preflight", "--profile", "any"])
            finally:
                os.environ.pop("HERMES_AGENTS_DATA_HOME", None)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["schema_version"], "hermes.state-doctor.v1")
            self.assertIn("profile", payload)
            self.assertEqual(err.getvalue(), "")
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()