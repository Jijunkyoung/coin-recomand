import unittest

from src.indicators import ema, mvrv_z_score, pct_change, rsi, volume_ratio


class IndicatorTests(unittest.TestCase):
    def test_rsi_for_rising_series(self):
        self.assertEqual(rsi(list(range(1, 40))), 100.0)

    def test_ema_needs_full_period(self):
        self.assertIsNone(ema([1, 2, 3], 5))
        self.assertAlmostEqual(ema([1, 2, 3, 4, 5], 5), 3.395061728, places=6)

    def test_percent_change(self):
        self.assertAlmostEqual(pct_change([100, 110, 121], 2), 21.0)

    def test_volume_ratio(self):
        volumes = [100.0] * 23 + [200.0] * 7
        self.assertAlmostEqual(volume_ratio(volumes), 2 / (37 / 30), places=6)

    def test_mvrv_z_score(self):
        markets = [float(value) for value in range(100, 140)]
        realized = [80.0] * 40
        score = mvrv_z_score(markets, realized)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)


if __name__ == "__main__":
    unittest.main()
