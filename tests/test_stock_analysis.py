import unittest

from src.stock_analysis import build_stock_report, market_regime, stock_score, technical_metrics


class FakeKisClient:
    configured = True

    def daily(self, _market, symbol, _exchange, _days):
        offset = 20 if symbol in {"SPY", "069500"} else 0
        return [
            {"date": f"2026-01-{index + 1:02d}", "open": 99 + index + offset, "high": 102 + index + offset,
             "low": 98 + index + offset, "price": 100 + index + offset, "volume": 1_000_000 + index * 20_000}
            for index in range(60)
        ]


class StockAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "history_days": 60, "recommendation_count": 1,
            "us": {"benchmark": {"symbol": "SPY", "name": "S&P", "exchange": "AMS"},
                   "universe": [{"symbol": "AAPL", "name": "애플", "exchange": "NAS"}]},
            "kr": {"benchmark": {"symbol": "069500", "name": "KODEX 200", "exchange": "KRX"},
                   "universe": [{"symbol": "005930", "name": "삼성전자", "exchange": "KRX"}]},
        }

    def test_report_has_ranking_history_and_score(self):
        report = build_stock_report("us", self.settings, FakeKisClient())
        self.assertEqual(report["status"], "정상")
        self.assertEqual(report["rankings"][0]["rank"], 1)
        self.assertEqual(len(report["rankings"][0]["history"]), 60)
        self.assertGreaterEqual(report["rankings"][0]["score"], 0)
        self.assertLessEqual(report["rankings"][0]["score"], 100)

    def test_unconfigured_client_returns_setup_report(self):
        client = FakeKisClient()
        client.configured = False
        report = build_stock_report("kr", self.settings, client)
        self.assertEqual(report["status"], "설정 필요")
        self.assertEqual(report["rankings"], [])
        self.assertIn("KIS_APP_KEY", report["warnings"][0])

    def test_metrics_and_market_regime(self):
        metrics = technical_metrics(FakeKisClient().daily("us", "AAPL", "NAS", 60))
        regime, score = market_regime(metrics)
        self.assertEqual(regime, "상승")
        self.assertGreaterEqual(score, 70)
        stock_points, reasons, _ = stock_score(metrics, regime)
        self.assertGreater(stock_points, 50)
        self.assertTrue(reasons)


if __name__ == "__main__":
    unittest.main()
