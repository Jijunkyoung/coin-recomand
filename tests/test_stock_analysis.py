import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.stock_analysis import build_stock_report, collect_stock_news, market_regime, parse_holdings, parse_sector_selection, selected_universe, stock_score, technical_metrics


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
        self.assertIsNotNone(report["rankings"][0]["return_1d"])

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

    def test_sector_and_holding_selection(self):
        self.settings["sectors"] = {
            "semiconductor": {"label": "반도체", "us": ["AAPL"], "kr": ["005930"]},
            "energy": {"label": "에너지", "us": [], "kr": []},
        }
        self.assertEqual(parse_sector_selection("SEMICONDUCTOR,unknown,energy", self.settings), ["semiconductor", "energy"])
        self.assertEqual([item["symbol"] for item in selected_universe("kr", self.settings, ["semiconductor"])], ["005930"])
        self.assertEqual([item["symbol"] for item in selected_universe("kr", self.settings, [])], ["005930"])
        holdings = parse_holdings("005930, 000660|하이닉스,invalid symbol", self.settings["kr"])
        self.assertEqual(holdings, [{"symbol": "005930", "name": "삼성전자"}, {"symbol": "000660", "name": "하이닉스"}])

    def test_empty_explicit_universe_requests_selection(self):
        self.settings["sectors"] = {"energy": {"label": "에너지", "us": [], "kr": []}}
        report = build_stock_report("kr", self.settings, FakeKisClient(), universe=[], selected_sectors=[])
        self.assertEqual(report["status"], "선택 필요")
        self.assertEqual(report["rankings"], [])

    def test_report_generator_keeps_full_catalog_searchable(self):
        source = Path("src/stock_analysis.py").read_text(encoding="utf-8")
        self.assertIn('list(settings[market].get("universe", []))', source)

    def test_stock_news_is_limited_to_holdings_and_selected_sectors(self):
        self.settings["sectors"] = {"semiconductor": {"label": "반도체", "news_terms": ["반도체"], "us": ["AAPL"], "kr": []}}
        published = format_datetime(datetime.now(timezone.utc))
        xml = f"""<rss><channel><item><title>애플 반도체 투자 확대 - 테스트뉴스</title><link>https://example.com/a</link><pubDate>{published}</pubDate><source>테스트뉴스</source></item><item><title>무관한 야구 소식 - 테스트뉴스</title><link>https://example.com/b</link><pubDate>{published}</pubDate><source>테스트뉴스</source></item></channel></rss>"""
        response = MagicMock(text=xml)
        response.raise_for_status.return_value = None
        session = MagicMock()
        session.get.return_value = response
        result = collect_stock_news({"us": [{"symbol": "AAPL", "name": "애플"}], "kr": []}, ["semiconductor"], self.settings, session=session)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["related_holdings"], ["AAPL"])
        self.assertEqual(result[0]["related_sectors"], ["반도체"])


if __name__ == "__main__":
    unittest.main()
