import unittest

from src.scoring import ALT_RAW_MAX_SCORE, alt_score, market_regime, normalize_alt_score, recommendation_label


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

    def test_theoretical_raw_max_is_normalized_to_100(self):
        metrics = {
            "price": 120, "ema20": 110, "ema50": 100, "rsi": 55, "macd_histogram": 1,
            "return_7d": 5, "return_30d": 15, "volume_ratio": 1.2, "volatility": 60,
            "trending_rank": 1, "community_total": 7, "community_sources": 3,
            "community_mentions": {"reddit": 3, "dcinside": 2, "coinpan": 2}, "community_exposure_rate": 3,
            "development": {"commits_30d": 30, "latest_release_days": 10},
            "tokenomics": {"circulating_ratio": 90},
        }
        score, _, _ = alt_score(metrics, "상승")
        self.assertEqual(ALT_RAW_MAX_SCORE, 77)
        self.assertEqual(score, 100)
        self.assertEqual(normalize_alt_score(77), 100)

    def test_normalized_thresholds_preserve_previous_decisions(self):
        self.assertEqual(recommendation_label(normalize_alt_score(67), "상승"), "분할매수 후보")
        self.assertEqual(recommendation_label(normalize_alt_score(66), "상승"), "관찰")
        self.assertEqual(recommendation_label(normalize_alt_score(51), "상승"), "보류")


if __name__ == "__main__":
    unittest.main()
