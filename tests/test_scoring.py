import unittest

from src.scoring import alt_score, market_regime, recommendation_label


class ScoringTests(unittest.TestCase):
    def test_bull_market(self):
        score, regime, reasons = market_regime({"price": 120, "ema20": 110, "ema50": 100, "return_30d": 12, "volume_ratio": 1.4, "mvrv_z": 1.5, "fear_greed": 55})
        self.assertEqual(regime, "상승")
        self.assertGreaterEqual(score, 65)
        self.assertTrue(reasons)

    def test_bear_market_blocks_buy_label(self):
        self.assertNotEqual(recommendation_label(99, "하락"), "분할매수 후보")

    def test_overheated_alt_is_penalized(self):
        healthy = {"price": 120, "ema20": 110, "ema50": 100, "rsi": 58, "macd_histogram": 1, "return_7d": 5, "return_30d": 15, "volume_ratio": 1.3, "volatility": 70, "trending_rank": 4}
        overheated = {**healthy, "rsi": 82, "return_7d": 35, "return_30d": 80, "volume_ratio": 4, "volatility": 150}
        healthy_score, _, _ = alt_score(healthy, "상승")
        overheated_score, _, risks = alt_score(overheated, "상승")
        self.assertGreater(healthy_score, overheated_score)
        self.assertTrue(risks)


if __name__ == "__main__":
    unittest.main()
