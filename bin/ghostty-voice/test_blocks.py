#!/usr/bin/env python3
"""Stdlib checks: Cos/Atop/plan never get send-keys or pane capture."""

from __future__ import annotations

import unittest

import lanes
import steer


BLOCKED = (
    "cos",
    "cos:0.0",
    "cos-voice",
    "cos-ao2:0.0",
    "cos-infra0",
    "atop",
    "atop:0.0",
    "atop-coord",
    "mac:0.0",
    "this",
    "pi",
    "pm",
    "pl",
    "notes",
    "claude",
    "cosw",
)


class BlockBoundary(unittest.TestCase):
    def test_inject_blocked_names(self) -> None:
        for target in BLOCKED:
            if lanes.session_name(target) == "mac":
                self.assertFalse(lanes.send_keys_allowed(target), target)
                continue
            self.assertTrue(lanes.inject_blocked(target), target)
            self.assertFalse(lanes.send_keys_allowed(target), target)
            self.assertFalse(lanes.capture_allowed(target), target)

    def test_inject_returns_before_tmux(self) -> None:
        for target in BLOCKED:
            result = lanes.inject("hello", target)
            self.assertFalse(result.get("ok"), target)
            self.assertIn("blocked", str(result.get("error") or ""))

    def test_pick_returns_before_tmux(self) -> None:
        for target in ("cos:0.0", "atop:0.0", "cos-ao2:0.0"):
            result = lanes.send_pick("y", target)
            self.assertFalse(result.get("ok"), target)
            self.assertIn("blocked", str(result.get("error") or ""))

    def test_capture_frame_blocked(self) -> None:
        frame = lanes.capture_frame("atop:0.0")
        self.assertTrue(frame.get("blocked"))
        self.assertFalse(frame.get("ok"))
        self.assertEqual(frame.get("text"), "")

    def test_cos_watch_not_keys(self) -> None:
        self.assertTrue(lanes.watch_allowed("cos:0.0"))
        self.assertFalse(lanes.send_keys_allowed("cos:0.0"))
        self.assertFalse(lanes.inject("hello", "cos:0.0").get("ok"))

    def test_workers_allowed(self) -> None:
        for session in lanes.WORKER_SESSIONS:
            self.assertTrue(lanes.send_keys_allowed(f"{session}:0.0"), session)
            self.assertTrue(lanes.capture_allowed(session), session)

    def test_new_dest_kinds_and_buffer(self) -> None:
        self.assertEqual(steer.dest_kind("this"), "pi")
        self.assertEqual(steer.dest_kind("claude"), "claude")
        self.assertEqual(steer.dest_kind("pm"), "herm_tui")
        self.assertEqual(steer.named_dest("chief continue"), "cos")
        self.assertEqual(steer.canonicalize_dest("caws"), "cos")
        self.assertEqual(steer.canonicalize_dest("COS"), "cos")
        self.assertEqual(steer.canonicalize_dest("C-O-S"), "cos")
        self.assertEqual(steer.named_dest("caws what's the status"), "cos")
        self.assertEqual(steer.named_dest("chief of staff continue"), "cos")
        self.assertEqual(steer.spoken_dest("caws"), "Chief of Staff")
        self.assertEqual(steer.dest_kind("caws"), "cos")
        self.assertNotEqual(steer.canonicalize_dest("cookie"), "cos")
        self.assertNotEqual(steer.canonicalize_dest("cause"), "cos")
        self.assertIsNone(steer.named_dest("because the cookie is ready"))
        self.assertEqual(steer.named_dest("send this to claude"), "claude")
        self.assertTrue(steer.is_buffer_request("into the buffer continue"))
        self.assertEqual(steer.dest_kind("cosw"), "unknown")
        self.assertFalse(lanes.send_keys_allowed("pi"))
        self.assertFalse(lanes.send_keys_allowed("notes"))

    def test_parse_prompt_reads_real_choices(self) -> None:
        menu = lanes.parse_prompt(
            "Do you want to proceed?\n❯ 1. Allow this time\n  2. Allow for this session\n  3. Deny\n",
            "ao2:0.0",
        )
        self.assertEqual(menu["kind"], "menu")
        self.assertEqual([row["key"] for row in menu["options"]], ["1", "2", "3"])
        self.assertEqual(menu["options"][0]["label"], "Allow this time")
        confirm = lanes.parse_prompt("permission needed\nDo you want to run this? [Y/n]\n", "ao1:0.0")
        self.assertEqual(confirm["kind"], "permission")
        self.assertEqual([row["key"] for row in confirm["options"]], ["y", "n"])
        self.assertIsNone(lanes.parse_prompt("idle worker just logging\nready.\n", "ao2:0.0"))
        self.assertIsNone(lanes.current_prompt("cos:0.0"))

    def test_buffer_preview_has_transport(self) -> None:
        preview = steer.buffer_preview("cos", last_text="steer line")
        self.assertEqual(preview["dest"], "cos")
        self.assertIn(preview["transport"], {"inbox", "nvim-buffer"})
        if not preview.get("path"):
            self.assertEqual(preview["text"], "steer line")

    def test_hint_does_not_steal_cos_voice_pane(self) -> None:
        self.assertTrue(steer._hint_matches("cos:2.7", "cos"))
        self.assertFalse(steer._hint_matches("cos-voice:0.0", "cos"))
        self.assertFalse(steer._hint_matches("cos-ao2:1.0", "cos"))
        self.assertTrue(steer.looks_like_tmux_pane("tmux:cos:0.0"))
        self.assertTrue(steer.looks_like_tmux_pane("this:0.0"))
        self.assertFalse(steer.looks_like_tmux_pane("hermes:chief-of-staff"))
        self.assertFalse(steer.looks_like_tmux_pane("20260913_054853_e9f8e4"))
        self.assertIsNotNone(steer.reject_operator_sid("cos", "tmux:cos:0.0"))
        self.assertIsNotNone(steer.reject_operator_sid("pi", "this:0.0"))
        self.assertIsNone(steer.reject_operator_sid("cos", "hermes:chief-of-staff"))
        sid = steer.resolve_cos_sid()
        self.assertFalse(steer.looks_like_tmux_pane(sid), sid)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
