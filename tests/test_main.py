import unittest
from unittest.mock import patch

from src.main import InsufficientHistoryError, build_report, technical_metrics, warning_reason


class MainAnalysisTests(unittest.TestCase):
    @staticmethod
    def candles():
        return [
            {
                "trade_price": 100 + index,
                "opening_price": 99 + index,
                "high_price": 102 + index,
                "low_price": 98 + index,
                "candle_acc_trade_price": 1_000_000 + index * 10_000,
                "candle_date_time_kst": f"2026-01-{(index % 28) + 1:02d}T00:00:00",
            }
            for index in range(60)
        ]

    def test_technical_metrics_contains_dated_history(self):
        result = technical_metrics(self.candles())
        self.assertEqual(len(result["history"]), 60)
        self.assertEqual(result["history"][0]["date"], "2026-01-01")
        self.assertIn("price", result["history"][0])
        self.assertEqual(result["history"][0]["open"], 99)
        self.assertEqual(result["history"][0]["high"], 102)
        self.assertEqual(result["history"][0]["low"], 98)
        self.assertIn("volume", result["history"][0])

    def test_short_history_error_explains_available_days(self):
        with self.assertRaisesRegex(InsufficientHistoryError, r"59일/최소 60일"):
            technical_metrics(self.candles()[:59])

    def test_http_403_warning_is_human_readable(self):
        error = RuntimeError()
        error.response = type("Response", (), {"status_code": 403})()
        self.assertEqual(warning_reason(error), "HTTP 403 접근 거부(수집 실행환경 제한)")

    @patch.dict("os.environ", {"MOBULA_API_KEY": "test"})
    @patch("src.main.time.sleep", return_value=None)
    def test_short_history_is_a_notice_not_a_provider_warning(self, _sleep):
        candles = self.candles()

        class FakeClient:
            def upbit_markets(self): return [{"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"}, {"market": "KRW-CP", "korean_name": "컨버전스", "english_name": "Convergence"}]
            def upbit_tickers(self, _markets): return [{"market": "KRW-CP", "acc_trade_price_24h": 10_000_000_000}]
            def upbit_daily_candles(self, market, _count): return candles if market == "KRW-BTC" else candles[:2]
            def bitcoin_mvrv_z(self): return 1.2
            def fear_and_greed(self): return {"value": 50, "classification": "Neutral", "previous": 48}
            def defillama_market_liquidity(self): return None
            def coingecko_trending(self): return {}
            def reddit_mentions(self, _aliases): return None, 0
            def dcinside_mentions(self, _aliases, _pages): return {}, 0
            def coinpan_mentions(self, _aliases, _pages): return {}, 0
            def crypto_news(self, _symbols, limit=7): return []
            def coinmarketcal_events(self, _symbols, limit=8): return []
            def coingecko_coin_list(self): return []

        settings = {"upbit_candle_days": 60, "excluded_symbols": ["BTC"], "minimum_24h_value_krw": 1, "screen_count": 1, "recommendation_count": 1, "fundamental_candidate_count": 1, "community_pages": 1}
        report = build_report(settings, FakeClient())
        self.assertEqual(report["data_quality"]["status"], "정상")
        self.assertEqual(report["data_quality"]["warnings"], [])
        self.assertEqual(report["data_quality"]["notices"], ["KRW-CP 분석 제외: 거래이력 부족 (2일/최소 60일)"])

    @patch("src.main.time.sleep", return_value=None)
    def test_report_combines_three_community_sources_and_project_context(self, _sleep):
        candles = self.candles()

        class FakeClient:
            def upbit_markets(self): return [{"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"}, {"market": "KRW-XRP", "korean_name": "리플", "english_name": "XRP"}]
            def upbit_tickers(self, _markets): return [{"market": "KRW-XRP", "acc_trade_price_24h": 10_000_000_000}]
            def upbit_daily_candles(self, _market, _count): return candles
            def bitcoin_mvrv_z(self): return 1.2
            def fear_and_greed(self): return {"value": 50, "classification": "Neutral", "previous": 48}
            def defillama_market_liquidity(self): return {"defi_tvl_usd": 100, "defi_tvl_change_7d": 2.5, "source": "DefiLlama"}
            def coingecko_trending(self): return {"XRP": 3}
            def reddit_mentions(self, _aliases): return {"XRP": 1}, 20
            def dcinside_mentions(self, _aliases, _pages): return {"XRP": 2}, 40
            def coinpan_mentions(self, _aliases, _pages): return {"XRP": 3}, 40
            def crypto_news(self, _symbols, limit=7): return [{"title": "XRP 이슈", "source": "테스트", "url": "https://example.com", "published_at": "2026-01-01T00:00:00+00:00", "published_at_kst": "01-01 09:00", "category": "시장", "impact": "중립·혼재", "related_symbols": ["XRP"]}]
            def coinmarketcal_events(self, _symbols, limit=8): return [{"id": "1", "title": "XRP 일정", "date": "2026-01-02", "date_kst": "01-02", "related_symbols": ["XRP"], "categories": [], "impact_score": None, "source": "CoinMarketCal"}]
            def coingecko_coin_list(self): return [{"id": "ripple", "symbol": "xrp", "name": "XRP"}]
            def coingecko_coin_details(self, _coin_id): return {"id": "ripple", "market_data": {"circulating_supply": 80, "total_supply": 100}, "links": {"repos_url": {"github": []}, "homepage": ["https://ripple.com"]}}

        settings = {"upbit_candle_days": 60, "excluded_symbols": ["BTC"], "minimum_24h_value_krw": 1, "screen_count": 1, "recommendation_count": 1, "fundamental_candidate_count": 1, "community_pages": 1}
        report = build_report(settings, FakeClient())
        coin = report["recommendations"][0]
        self.assertEqual(report["alt_rankings"][0]["rank"], 1)
        self.assertEqual(report["alt_rankings"][0]["symbol"], "XRP")
        self.assertEqual(len(report["alt_rankings"][0]["history"]), 60)
        self.assertEqual(len(report["alt_rankings"][0]["sparkline"]), 30)
        self.assertEqual(coin["community_total"], 6)
        self.assertEqual(coin["community_sources"], 3)
        self.assertEqual(coin["development"]["status"], "공개 GitHub 없음")
        self.assertEqual(coin["tokenomics"]["circulating_ratio"], 80.0)
        self.assertEqual(report["news_issues"][0]["related_symbols"], ["XRP"])
        self.assertEqual(report["market"]["liquidity"]["defi_tvl_change_7d"], 2.5)
        self.assertEqual(report["upcoming_events"][0]["related_symbols"], ["XRP"])
        self.assertEqual(report["methodology"]["groups"][0]["range"], "원점수 -18 ~ +22")


if __name__ == "__main__":
    unittest.main()
