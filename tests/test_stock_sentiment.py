import copy
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import patch

from src.stock_sentiment import add_market_context, benchmark_indicators, parse_cnn, parse_csv, proxy_sentiment

NOW = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)


def benchmark(direction=1, length=100):
    return {"name": "Test ETF", "history": [
        {"date": (NOW - timedelta(days=length - index)).strftime("%Y-%m-%d"),
         "price": 200 + direction * index + math.sin(index) * .2}
        for index in range(length)]}


class StockSentimentTests(unittest.TestCase):
    def test_proxy_bounds_and_direction_and_flat_neutral(self):
        rising = proxy_sentiment(benchmark(1), "kr", NOW)
        falling = proxy_sentiment(benchmark(-1), "kr", NOW)
        self.assertGreater(rising["score"], falling["score"])
        for item in [rising, falling]:
            self.assertEqual(item["kind"], "proxy")
            self.assertEqual(len(item["components"]), 4)
            self.assertTrue(all(0 <= row["value"] <= 100 for row in item["history"]))
        flat = benchmark()
        for row in flat["history"]:
            row["price"] = 100
        self.assertEqual(proxy_sentiment(flat, "kr", NOW)["score"], 50)

    def test_history_uses_no_future_prices(self):
        original = benchmark()
        before = proxy_sentiment(original, "us", NOW)["history"]
        changed = copy.deepcopy(original)
        changed["history"][-1]["price"] *= .4
        after = proxy_sentiment(changed, "us", NOW)["history"]
        self.assertEqual(before[:-1], after[:-1])
        self.assertNotEqual(before[-1]["value"], after[-1]["value"])

    def test_insufficient_history_is_missing_not_neutral(self):
        result = proxy_sentiment(benchmark(length=50), "kr", NOW)
        self.assertIsNone(result["score"])
        self.assertEqual(result["history"], [])

    def test_cnn_zero_score_is_valid_and_old_observation_is_flagged(self):
        result = parse_cnn({"fear_and_greed": {"score": 0, "previous_close": 10, "timestamp": "2026-11-01T20:00:00Z"}}, NOW)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["kind"], "published")
        self.assertEqual(result["change"], -10)
        self.assertTrue(result["stale"])

    def test_cnn_invalid_future_or_missing_values_are_not_used(self):
        for current in [{"score": 101, "timestamp": NOW.isoformat()},
                        {"score": "NaN", "timestamp": NOW.isoformat()},
                        {"score": 60, "timestamp": "2026-12-01T10:00:00Z"},
                        {"score": 60, "timestamp": "2026-11-20T10:00:00"}]:
            with self.assertRaises((ValueError, TypeError)):
                parse_cnn({"fear_and_greed": current}, NOW)

    def test_daily_csv_skips_holidays_nonfinite_and_future_observations(self):
        rows = parse_csv("observation_date,DGS10\n2026-11-17,5.10\n2026-11-18,.\n2026-11-19,NaN\n2026-11-21,6.0\n", "DGS10", NOW)
        self.assertEqual(rows, [{"date": "2026-11-17", "value": 5.1}])
        vix = parse_csv("DATE,OPEN,CLOSE\n11/18/2026,23.4,24.56\n", "CLOSE", NOW, vix=True)
        self.assertEqual(vix[-1], {"date": "2026-11-18", "value": 24.56})

    def test_breadth_is_limited_to_dated_analyzed_symbols(self):
        bench = benchmark()
        date = bench["history"][-1]["date"]
        report = {"benchmark": bench, "rankings": [
            {"price": 110, "ema50": 100, "history": [{"date": date}]},
            {"price": 90, "ema50": 100, "history": [{"date": date}]},
            {"price": 110, "ema50": 100, "history": [{"date": "2026-01-01"}]},
        ]}
        card = next(item for item in benchmark_indicators(report, NOW) if item["id"] == "breadth")
        self.assertEqual(card["value"], 50)
        self.assertIn("2개 중 1개", card["note"])

    @patch("src.stock_sentiment._download", side_effect=RuntimeError("offline"))
    def test_source_outage_falls_back_to_labeled_proxy_without_changing_stock_scores(self, download):
        reports = {market: {"benchmark": benchmark(), "rankings": [], "market_score": 80} for market in ["us", "kr"]}
        add_market_context(reports, NOW)
        for market in reports:
            self.assertEqual(reports[market]["market_score"], 80)
            self.assertEqual(reports[market]["market_context"]["sentiment"]["kind"], "proxy")
        self.assertIn("CNN", reports["us"]["market_context"]["sentiment"]["notice"])
        self.assertIsNone(reports["us"]["market_context"]["indicators"][0]["value"])
        self.assertIsNone(reports["kr"]["market_context"]["indicators"][0]["value"])

    @patch("src.stock_sentiment._download")
    def test_published_cnn_preferred_and_rates_use_basis_points(self, download):
        published = parse_cnn({"fear_and_greed": {"score": 20, "timestamp": NOW.isoformat()}}, NOW)
        rows = [{"date": "2026-11-17", "value": 5.0}, {"date": "2026-11-18", "value": 5.1}]
        download.side_effect = lambda name, now: published if name == "cnn" else rows
        reports = {market: {"benchmark": benchmark(), "rankings": []} for market in ["us", "kr"]}
        add_market_context(reports, NOW)
        self.assertEqual(reports["us"]["market_context"]["sentiment"]["kind"], "published")
        self.assertEqual(reports["kr"]["market_context"]["sentiment"]["kind"], "proxy")
        yield_card = next(item for item in reports["us"]["market_context"]["indicators"] if item["id"] == "us10y")
        self.assertEqual(yield_card["change"], 10)
        self.assertEqual(yield_card["change_unit"], "bp")


if __name__ == "__main__":
    unittest.main()
