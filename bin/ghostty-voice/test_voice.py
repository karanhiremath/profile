#!/usr/bin/env python3
"""Cos-voice default vs dest-distinct Cartesia ids. No network."""

from __future__ import annotations

import unittest

import cartesia


class VoiceAssignment(unittest.TestCase):
    def test_cos_default(self) -> None:
        self.assertEqual(
            cartesia.DEFAULT_COS_VOICE_ID,
            "f6141af3-5f94-418c-80ed-a45d450e7e2e",
        )
        self.assertEqual(cartesia.resolve_voice({}, dest="cos"), cartesia.DEFAULT_COS_VOICE_ID)
        self.assertEqual(cartesia.resolve_voice({}, dest="brief"), cartesia.DEFAULT_COS_VOICE_ID)
        self.assertEqual(
            cartesia.resolve_voice({"CARTESIA_VOICE_ID": "override"}, dest="cos"),
            "override",
        )

    def test_other_dests_do_not_reuse_cos_default(self) -> None:
        self.assertEqual(cartesia.resolve_voice({}, dest="ao2"), "")
        self.assertEqual(
            cartesia.resolve_voice({"CARTESIA_VOICE_ID_AO2": "ao2-voice"}, dest="ao2"),
            "ao2-voice",
        )
        self.assertEqual(
            cartesia.resolve_voice({"CARTESIA_VOICE_ID": cartesia.DEFAULT_COS_VOICE_ID}, dest="notes"),
            "",
        )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
