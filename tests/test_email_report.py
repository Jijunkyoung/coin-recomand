import unittest

from src.email_report import build_email_html, parse_recipients


class EmailReportTests(unittest.TestCase):
    def test_parses_multiple_recipient_formats_and_removes_duplicates(self):
        value = "first@example.com\nSECOND@example.com;first@example.com,third@example.com"
        self.assertEqual(parse_recipients(value), ["first@example.com", "SECOND@example.com", "third@example.com"])

    def test_rejects_invalid_recipient(self):
        with self.assertRaisesRegex(ValueError, "잘못된 수신 이메일 주소"):
            parse_recipients("valid@example.com,not-an-email")

    def test_email_contains_news_issue_and_escaped_link(self):
        report = {
            "generated_at_kst": "2026-09-11 07:30 KST",
            "market": {
                "regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2},
                "liquidity": {"defi_tvl_usd": 100_000_000_000, "defi_tvl_change_7d": 2.5, "stablecoin_supply_usd": 200_000_000_000, "stablecoin_supply_change_7d": -0.2},
            },
            "recommendations": [],
            "news_issues": [{
                "title": "BTC 주요 이슈", "source": "테스트 뉴스", "url": "https://example.com/?a=1&b=2",
                "published_at_kst": "09-11 07:00", "category": "ETF·기관", "impact": "호재 가능",
                "related_symbols": ["BTC"],
            }],
            "upcoming_events": [{"title": "XRP 네트워크 업그레이드", "date_kst": "09-13", "related_symbols": ["XRP"], "categories": ["Release"], "impact_score": None}],
        }
        result = build_email_html(report)
        self.assertIn("최근 24시간 주요 코인 이슈", result)
        self.assertIn("BTC 주요 이슈", result)
        self.assertIn("a=1&amp;b=2", result)
        self.assertIn("DeFi TVL", result)
        self.assertIn("향후 7일 주요 일정", result)
        self.assertIn("XRP 네트워크 업그레이드", result)

    def test_email_contains_stock_recommendations(self):
        report = {
            "generated_at_kst": "2026-09-12 07:30 KST",
            "market": {"regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2}, "liquidity": {}},
            "recommendations": [], "news_issues": [], "upcoming_events": [],
        }
        stocks = {"us": {"market_name": "미국주식", "regime": "상승", "market_score": 80,
                         "recommendations": [{"name": "애플", "symbol": "AAPL", "score": 82, "decision": "분할매수 후보", "rsi": 58, "return_30d": 9}]},
                  "kr": {"market_name": "국내주식", "warnings": ["설정 필요"], "recommendations": []}}
        result = build_email_html(report, stocks)
        self.assertIn("미국주식 추천", result)
        self.assertIn("애플", result)
        self.assertIn("국내주식", result)


if __name__ == "__main__":
    unittest.main()
