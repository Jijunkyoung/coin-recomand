import unittest

from src.main import technical_metrics


class MainAnalysisTests(unittest.TestCase):
    def test_technical_metrics_contains_dated_history(self):
        candles = [
            {
                "trade_price": 100 + index,
                "candle_acc_trade_price": 1_000_000 + index * 10_000,
                "candle_date_time_kst": f"2026-01-{(index % 28) + 1:02d}T00:00:00",
            }
            for index in range(60)
        ]
        result = technical_metrics(candles)
        self.assertEqual(len(result["history"]), 60)
        self.assertEqual(result["history"][0]["date"], "2026-01-01")
        self.assertIn("price", result["history"][0])
        self.assertIn("volume", result["history"][0])


if __name__ == "__main__":
    unittest.main()
