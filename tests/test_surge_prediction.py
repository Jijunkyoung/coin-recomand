import copy
import unittest
from datetime import date, timedelta

from src.surge_prediction import (
    _btc_context,
    _clean_history,
    build_samples,
    build_surge_research,
    feature_snapshot,
    surge_label,
)


def history(days=100, offset=0, bitcoin=False):
    rows = []
    close = 100 + offset
    start = date(2026, 1, 1)
    for index in range(days):
        previous = close
        if bitcoin:
            close = previous * 1.0005
            high = close * 1.01
            volume = 100_000_000_000
        elif index % 10 == 9:
            close = previous * 1.03
            high = close * 1.02
            volume = 2_000_000_000
        elif index % 10 == 0 and index:
            close = previous * 1.04
            high = previous * 1.13
            volume = 3_500_000_000
        else:
            close = previous * 1.001
            high = close * 1.015
            volume = 1_000_000_000
        rows.append({
            "date": (start + timedelta(days=index)).isoformat(),
            "open": round(previous, 6),
            "high": round(high, 6),
            "low": round(min(previous, close) * 0.99, 6),
            "price": round(close, 6),
            "volume": volume,
        })
    return rows


class SurgePredictionTests(unittest.TestCase):
    def setUp(self):
        self.bitcoin = history(bitcoin=True)
        self.coins = [
            {
                "market": f"KRW-C{index}", "symbol": f"C{index}", "name": f"코인{index}",
                "price": 200 + index, "rsi": 60, "trade_value_24h": 8_000_000_000 + index,
                "history": history(offset=index),
                "development": {"commits_30d": 30 if index == 0 else 2, "status": "활발"},
            }
            for index in range(7)
        ]

    def test_features_never_read_the_following_candle(self):
        rows = _clean_history(history())
        btc = _btc_context(self.bitcoin)
        before = feature_snapshot(rows, 60, btc)
        changed = copy.deepcopy(rows)
        changed[61]["close"] = 999999
        changed[61]["high"] = 999999
        changed[61]["volume"] = 999999999999
        self.assertEqual(before, feature_snapshot(changed, 60, btc))

    def test_open_latest_daily_candle_is_never_a_training_label(self):
        original = build_samples(self.coins[:1], self.bitcoin)
        changed_coin = copy.deepcopy(self.coins[:1])
        changed_coin[0]["history"][-1].update(price=999999, high=999999, volume=999999999999)
        self.assertEqual(original, build_samples(changed_coin, self.bitcoin))

    def test_label_requires_price_volume_and_btc_excess(self):
        rows = _clean_history(history())
        btc = _btc_context(self.bitcoin)
        self.assertEqual(surge_label(rows, 39, btc), 1)
        no_volume = copy.deepcopy(rows)
        no_volume[40]["volume"] = 500_000_000
        self.assertEqual(surge_label(no_volume, 39, btc), 0)

    def test_model_trains_with_time_split_and_ranks_candidates(self):
        result = build_surge_research(
            self.coins,
            self.bitcoin,
            [{"title": "C0 메인넷 발표", "importance": "높음", "related_symbols": ["C0"], "source_url": "https://example.com"}],
        )
        self.assertEqual(result["status"], "실험 학습 완료·수익성 미검증")
        self.assertGreater(result["samples"], 400)
        self.assertGreater(result["positive_samples"], 12)
        self.assertIsNotNone(result["validation"])
        self.assertLess(result["validation"]["split_date"], max(row["date"] for row in self.bitcoin))
        self.assertEqual(len(result["candidates"]), 7)
        self.assertTrue(all(0 <= row["model_probability_pct"] <= 100 for row in result["candidates"]))
        c0 = next(row for row in result["candidates"] if row["symbol"] == "C0")
        self.assertIn("30일 커밋", c0["development_signal"])
        self.assertEqual(c0["related_events"][0]["importance"], "높음")

    def test_insufficient_history_does_not_invent_predictions(self):
        result = build_surge_research(self.coins[:1], self.bitcoin[:50])
        self.assertEqual(result["status"], "학습 자료 부족")
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["validation"])


if __name__ == "__main__":
    unittest.main()
