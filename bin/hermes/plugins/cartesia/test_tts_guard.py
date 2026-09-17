#!/usr/bin/env python3
from __future__ import annotations

import unittest

from _tts_guard import filter_transcript


class TtsGuardTests(unittest.TestCase):
    def test_stall(self):
        out = filter_transcript("I'm working on it.")
        self.assertNotIn("working on it", out.lower())

    def test_timeout(self):
        out = filter_transcript("Chief of Staff did not reply")
        self.assertNotIn("did not reply", out.lower())

    def test_keeps_real_work(self):
        text = "I'm working on the auth patch."
        self.assertEqual(filter_transcript(text), text)


if __name__ == "__main__":
    unittest.main()
