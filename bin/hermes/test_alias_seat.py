#!/usr/bin/env python3
"""Isolation-seat unit tests. No live Cos/tmux attach."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import alias_seat as seat


class AliasSeatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.data = Path(self.tmp.name) / "data"
        self.home.mkdir()
        self.data.mkdir()
        self.saved = {
            key: os.environ.get(key)
            for key in ("HOME", "XDG_DATA_HOME", "HERMES_AGENTS_DATA_HOME", "HERMES_ALIAS_PIN")
        }
        os.environ["HOME"] = str(self.home)
        os.environ["XDG_DATA_HOME"] = str(self.data)
        os.environ.pop("HERMES_AGENTS_DATA_HOME", None)
        os.environ.pop("HERMES_ALIAS_PIN", None)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_cos_and_cos_m_share_one_home_and_session(self) -> None:
        desktop = seat.resolve_alias("cos")
        mobile = seat.resolve_alias("cos-m")
        self.assertEqual(desktop["profile"], "chief-of-staff")
        self.assertEqual(mobile["profile"], "chief-of-staff")
        self.assertEqual(desktop["root"], mobile["root"])
        self.assertEqual(desktop["session"], "cos")
        self.assertEqual(mobile["session"], "cos")
        self.assertEqual(desktop["window"], "0")
        self.assertEqual(mobile["window"], "m")
        self.assertTrue(desktop["root"].endswith("hermes-agents/chief-of-staff"))
        self.assertNotEqual(desktop["root"], str(Path(self.home) / ".hermes"))

    def test_cos_and_cosw_do_not_share_homes(self) -> None:
        cos = seat.resolve_alias("cos")
        cosw = seat.resolve_alias("cosw")
        self.assertNotEqual(cos["root"], cosw["root"])
        self.assertNotEqual(cos["session"], cosw["session"])
        self.assertEqual(cos["lane"], "personal")
        self.assertEqual(cosw["lane"], "work")

    def test_notes_family_isolated(self) -> None:
        notes = seat.resolve_alias("notes-m")
        notesw = seat.resolve_alias("notesw")
        self.assertEqual(notes["profile"], "personal-notes-steward")
        self.assertEqual(notesw["profile"], "work-notes-steward")
        self.assertNotEqual(notes["root"], notesw["root"])

    def test_unknown_alias_fails(self) -> None:
        with self.assertRaises(SystemExit):
            seat.resolve_alias("factory")

    def test_lock_ignores_dead_pid_and_reads_nested_runtime(self) -> None:
        profile = "chief-of-staff"
        runtime = seat.runtime_home(profile)
        runtime.mkdir(parents=True)
        (runtime / ".herm-tui.lock").write_text("999999\n", encoding="utf-8")
        self.assertIsNone(seat.lock_pid(profile))
        self.assertEqual(seat.clear_stale_locks(profile), [str(runtime / ".herm-tui.lock")])

    def test_lock_detects_live_pid(self) -> None:
        profile = "chief-of-staff"
        path = seat.write_lock(profile, os.getpid())
        self.assertTrue(path.exists())
        self.assertEqual(seat.lock_pid(profile), os.getpid())

    def test_write_seat_pins_family(self) -> None:
        path = seat.write_seat("chief-of-staff", "cos-m")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["family"], "cos")
        self.assertEqual(data["profile"], "chief-of-staff")
        self.assertTrue(data["pinned"])
        self.assertIn("cos", data["aliases"])
        self.assertIn("cos-m", data["aliases"])

    def test_homes_conflict_when_seat_family_mismatches(self) -> None:
        root = seat.isolated_root("chief-of-staff")
        root.mkdir(parents=True)
        (root / seat.SEAT_FILENAME).write_text(
            json.dumps({"family": "cosw", "pinned": True}),
            encoding="utf-8",
        )
        conflicts = seat.homes_conflict("chief-of-staff")
        self.assertTrue(conflicts)

    def test_inbox_homes_never_include_dot_hermes(self) -> None:
        homes = [str(path) for path in seat.inbox_homes("chief-of-staff")]
        self.assertTrue(homes)
        for home in homes:
            self.assertNotIn("/.hermes", home)
            self.assertNotEqual(home, str(self.home / ".hermes"))

    def test_assert_not_fallback_home(self) -> None:
        fallback = self.home / ".hermes"
        fallback.mkdir()
        with self.assertRaises(SystemExit):
            seat.assert_not_fallback_home(fallback)
        with self.assertRaises(SystemExit):
            seat.assert_not_fallback_home(fallback / "profiles" / "project-manager")
        isolated = seat.isolated_root("chief-of-staff")
        isolated.mkdir(parents=True)
        seat.assert_not_fallback_home(isolated)

    def test_pin_env_sets_runtime_and_flag(self) -> None:
        env = seat.pin_env("cos")
        self.assertEqual(env["HERMES_ALIAS_PIN"], "1")
        self.assertEqual(env["HERMES_ALIAS"], "cos")
        self.assertEqual(env["HERMES_PROFILE"], "chief-of-staff")
        self.assertTrue(env["HERMES_HOME"].endswith("chief-of-staff") or "profiles/chief-of-staff" in env["HERMES_HOME"])

    def test_attach_target_prefers_lock_pid_in_alias_session(self) -> None:
        seat.write_lock("chief-of-staff", os.getpid())
        panes = [
            {
                "session": "notes",
                "window": "0",
                "index": "0",
                "pid": str(os.getpid()),
                "command": "herm",
                "target": "notes:0.0",
            },
            {
                "session": "cos",
                "window": "0",
                "index": "0",
                "pid": str(os.getpid()),
                "command": "herm",
                "target": "cos:0.0",
            },
        ]
        with mock.patch.object(seat, "list_tmux_panes", return_value=panes):
            with mock.patch.object(seat, "pid_in_tree", return_value=True):
                self.assertEqual(seat.attach_target("chief-of-staff", "cos"), "cos:0.0")

    def test_attach_target_does_not_use_mobile_window_when_desktop_holds_tui(self) -> None:
        seat.write_lock("chief-of-staff", os.getpid())
        panes = [
            {
                "session": "cos",
                "window": "m",
                "index": "0",
                "pid": "999999",
                "command": "zsh",
                "target": "cos:m.0",
            },
            {
                "session": "cos",
                "window": "0",
                "index": "0",
                "pid": str(os.getpid()),
                "command": "herm",
                "target": "cos:0.0",
            },
        ]
        with mock.patch.object(seat, "list_tmux_panes", return_value=panes):
            with mock.patch.object(seat, "pid_in_tree", side_effect=lambda root, wanted: root == os.getpid()):
                self.assertEqual(seat.attach_target("chief-of-staff"), "cos:0.0")

    def test_lane_profiles_do_not_share_homes_or_sessions(self) -> None:
        main = seat.resolve_profile("chief-of-staff")
        o1 = seat.resolve_profile("chief-of-staff-o1")
        o2 = seat.resolve_profile("chief-of-staff-o2")
        work = seat.resolve_profile("chief-of-staff-work-o1")
        self.assertEqual(o1["instance"], "o1")
        self.assertEqual(o1["session"], "cos-o1")
        self.assertEqual(o2["session"], "cos-o2")
        self.assertEqual(work["session"], "cosw-o1")
        self.assertEqual(work["family"], "cosw")
        self.assertNotEqual(main["root"], o1["root"])
        self.assertNotEqual(o1["root"], o2["root"])
        self.assertNotEqual(o1["root"], work["root"])
        self.assertTrue(o1["root"].endswith("hermes-agents/chief-of-staff-o1"))
        self.assertEqual(seat.instance_profile("cos", "o1"), "chief-of-staff-o1")
        self.assertEqual(seat.instance_profile("cosw", "o1"), "chief-of-staff-work-o1")

    def test_work_prefix_wins_over_personal_prefix(self) -> None:
        parsed = seat.parse_instance_profile("chief-of-staff-work-o1")
        self.assertIsNotNone(parsed)
        base, instance = parsed
        self.assertEqual(base["family"], "cosw")
        self.assertEqual(instance, "o1")

    def test_lane_work_collision_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            seat.instance_profile("chief-of-staff", "work")
        with self.assertRaises(SystemExit):
            seat.instance_profile("cos", "../x")

    def test_write_seat_lane_stays_on_lane_home(self) -> None:
        path = seat.write_seat("chief-of-staff-o1", "cos")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["profile"], "chief-of-staff-o1")
        self.assertEqual(data["session"], "cos-o1")
        self.assertEqual(data["instance"], "o1")
        self.assertTrue(str(path).endswith("hermes-agents/chief-of-staff-o1/alias.seat.json"))
        main_root = seat.isolated_root("chief-of-staff")
        self.assertFalse((main_root / seat.SEAT_FILENAME).exists())

    def test_pin_env_profile_uses_lane_home(self) -> None:
        env = seat.pin_env("chief-of-staff-o1")
        self.assertEqual(env["HERMES_PROFILE"], "chief-of-staff-o1")
        self.assertEqual(env["HERMES_ALIAS_SESSION"], "cos-o1")
        self.assertEqual(env["HERMES_LANE"], "o1")
        self.assertTrue(
            env["HERMES_HOME"].endswith("chief-of-staff-o1")
            or "profiles/chief-of-staff-o1" in env["HERMES_HOME"]
        )
        main = seat.pin_env("cos")
        self.assertNotEqual(env["HERMES_HOME"], main["HERMES_HOME"])


if __name__ == "__main__":
    unittest.main()
