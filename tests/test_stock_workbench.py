import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

from src.stock_analysis import KisDataClient
from src.stock_workbench import attach_themes, parse_theme_news, screening_metrics

NOW = datetime(2026, 11, 25, 2, tzinfo=timezone.utc)


def history(count=260):
    return [{"date": (NOW-timedelta(days=count-i)).date().isoformat(), "price": 100+i,
             "high": 102+i, "low": 98+i, "volume": 1000} for i in range(count)]


class StockWorkbenchTests(unittest.TestCase):
    def test_missing_history_is_not_a_fake_52_week_or_200_day_statistic(self):
        row = screening_metrics(history(100), NOW)
        self.assertIsNotNone(row["sma50"])
        self.assertIsNone(row["sma200"])
        self.assertIsNone(row["high_52w"])
        self.assertIsNone(row["return_126"])
        row = screening_metrics(history(), NOW)
        self.assertEqual(row["high_52w"], 361)
        self.assertAlmostEqual(row["return_21"], (359/338-1)*100)
        self.assertEqual(row["estimated_turnover"], 359000)

    def test_screening_skips_future_bad_and_duplicate_prices(self):
        rows = history(60)
        rows += [rows[-1], {"date": "invalid", "price": 50}, {"date": "2027-01-01", "price": 1}, {"date": "2026-01-01", "price": "NaN"}]
        self.assertEqual(screening_metrics(rows, NOW)["observations"], 60)

    def test_themes_use_same_date_denominator_and_leave_scores_unchanged(self):
        rows = history(60)
        report = {"market": "us", "benchmark": {"name": "SPY", "return_1d": 1, "history": rows}, "rankings": [
            {"symbol": "A", "name": "A", "history": rows, "return_1d": 2, "score": 60},
            {"symbol": "B", "name": "B", "history": rows, "return_1d": -2, "score": 30},
            {"symbol": "C", "name": "C", "history": rows[:-1], "return_1d": 50, "score": 90}]}
        settings = {"sectors": {"test": {"label": "Test", "us": ["A", "B", "C", "D"]}}}
        attach_themes(report, settings, [], NOW)
        theme = report["theme_board"]["themes"][0]
        self.assertEqual((theme["count"], theme["expected_count"]), (2, 4))
        self.assertEqual(theme["return_1d"], 0)
        self.assertEqual(theme["relative"], -1)
        self.assertEqual(theme["breadth"], 50)
        self.assertEqual([x["symbol"] for x in theme["leaders"]], ["A", "B"])
        self.assertEqual(report["rankings"][0]["score"], 60)

    def test_public_news_has_strict_24h_window_and_requires_publication_time(self):
        valid = format_datetime(NOW-timedelta(hours=23))
        old = format_datetime(NOW-timedelta(hours=25))
        xml = f'<rss><channel><item><title>Fresh</title><link>https://example.com/f</link><pubDate>{valid}</pubDate></item><item><title>Old</title><link>https://example.com/o</link><pubDate>{old}</pubDate></item><item><title>No timestamp</title><link>https://example.com/n</link></item></channel></rss>'
        self.assertEqual([x["title"] for x in parse_theme_news(xml, "test", "Test", NOW)], ["Fresh"])

    @patch("src.stock_analysis.time.sleep")
    def test_overseas_history_pages_are_ordered_deduplicated_and_bounded(self, sleep):
        rows = history()
        def api_row(row):
            return {"xymd": row["date"].replace("-", ""), "clos": str(row["price"]), "open": "100", "high": "400", "low": "90", "tvol": "100"}
        pages = [list(reversed(rows[160:])), list(reversed(rows[60:161])), list(reversed(rows[:61]))]
        client = KisDataClient()
        with patch.object(client, "_get", side_effect=[{"output2": [api_row(x) for x in page]} for page in pages]) as get:
            result = client.overseas_daily("AAPL", "NAS", 260)
            self.assertEqual(len(result), 260)
            self.assertEqual(result[-1]["date"], rows[-1]["date"])
            self.assertEqual(get.call_count, 3)
            self.assertEqual(get.call_args_list[1].args[2]["BYMD"], (datetime.fromisoformat(rows[160]["date"])-timedelta(days=1)).strftime("%Y%m%d"))


if __name__ == "__main__": unittest.main()
