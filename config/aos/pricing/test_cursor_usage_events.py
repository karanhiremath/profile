#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

from cursor_usage_events import bucket_rates, classify, ingest_csv_path, parse_export_url, usd_per_m

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures/cursor-usage-events.sample.csv"
EXPORT_URL = (
    "https://cursor.com/api/dashboard/export-usage-events-csv"
    "?teamId=0&isEnterprise=true&startDate=1788912000000&endDate=1789516799999&strategy=tokens"
)


class CursorUsageEventsTest(unittest.TestCase):
    def test_classifies_dashboard_slugs(self) -> None:
        self.assertEqual(classify("cursor-grok-4.6-xhigh-fast"), "grok-4.6:fast")
        self.assertEqual(classify("cursor-grok-4.6-high-fast"), "grok-4.6:fast")
        self.assertEqual(classify("cursor-grok-4.6-xhigh"), "grok-4.6")
        self.assertEqual(usd_per_m("grok-4.6:fast"), 1.45)
        self.assertEqual(usd_per_m("grok-4.6"), 0.68)
        self.assertEqual(classify("together/deepseek-ai/DeepSeek-V4-Flash-0731"), "deepseek-v4-flash-0731")
        self.assertEqual(bucket_rates("deepseek-v4-flash-0731")["input"], 0.14)
        self.assertEqual(bucket_rates("deepseek-v4-flash-0731")["output"], 0.28)

    def test_parse_export_url(self) -> None:
        meta = parse_export_url(EXPORT_URL)
        self.assertTrue(meta["is_enterprise"])
        self.assertEqual(meta["strategy"], "tokens")
        self.assertEqual(meta["start_ms"], 1788912000000)
        self.assertTrue(meta["team_id_present"])

    def test_ingest_partitions_and_prices(self) -> None:
        payload = ingest_csv_path(FIXTURE, fees={"grok-4.6:fast": 0.07, "grok-4.6": 0.03})
        fast = payload["by_model"]["grok-4.6:fast"]
        slow = payload["by_model"]["grok-4.6"]
        self.assertEqual(fast["tokens"]["input"], 750000)
        self.assertEqual(fast["tokens"]["cache_read"], 300000)
        self.assertEqual(fast["tokens"]["output"], 75000)
        self.assertEqual(fast["tokens"]["billed"], 1125000)
        self.assertAlmostEqual(fast["cost"]["api_equivalent_usd"], 1.45 * 1.125, places=9)
        self.assertAlmostEqual(slow["cost"]["api_equivalent_usd"], 0.68, places=9)
        self.assertTrue(payload["dashboard_cost_is_included"])
        self.assertNotIn("User", str(payload["by_model"]))


if __name__ == "__main__":
    unittest.main()
