import unittest
from unittest.mock import patch

from src.email_report import build_email_html, build_stock_email_html, email_subject, parse_recipients, send_email, stock_email_subject


class EmailReportTests(unittest.TestCase):
    def test_parses_multiple_recipient_formats_and_removes_duplicates(self):
        value = "first@example.com\nSECOND@example.com;first@example.com,third@example.com"
        self.assertEqual(parse_recipients(value), ["first@example.com", "SECOND@example.com", "third@example.com"])

    def test_rejects_invalid_recipient(self):
        with self.assertRaisesRegex(ValueError, "잘못된 수신 이메일 주소"):
            parse_recipients("valid@example.com,not-an-email")

    def test_test_email_subject_is_clearly_marked(self):
        report = {"generated_at_kst": "2026-09-15 13:00 KST", "market": {"regime": "중립"}}
        self.assertEqual(email_subject(report, True), "[테스트] [중립] 코인 분석 2026-09-15")

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
            "major_events": [{
                "title": "미국 CLARITY 법안 관련 표결 일정", "importance": "매우 높음", "status": "확인 필요",
                "date": "2026-09-16", "days_until": 5, "related_symbols": ["BTC", "ETH"],
                "summary": "공식 표결 단계를 확인해야 합니다.", "source": "Congress.gov",
                "source_url": "https://www.congress.gov/bill/119th-congress/house-bill/3633",
            }],
        }
        result = build_email_html(report)
        self.assertIn("최근 24시간 주요 코인 이슈", result)
        self.assertIn("오늘의 코인 분석", result)
        self.assertNotIn("오늘의 코인·주식 분석", result)
        self.assertIn("BTC 주요 이슈", result)
        self.assertIn("a=1&amp;b=2", result)
        self.assertIn("DeFi TVL", result)
        self.assertIn("향후 7일 주요 일정", result)
        self.assertIn("XRP 네트워크 업그레이드", result)
        self.assertIn("주요 시장 이벤트", result)
        self.assertIn("미국 CLARITY 법안 관련 표결 일정", result)
        self.assertIn("결과 확인 전에는 추천 점수에 가산하지 않고", result)
        self.assertIn('name="color-scheme" content="light"', result)
        self.assertIn('bgcolor="#f3f6fb"', result)
        self.assertIn("color:#10233f", result)
        self.assertNotIn("background:#06101f", result)
        self.assertNotIn("background:linear-gradient", result)

    def test_email_contains_stock_recommendations(self):
        report = {
            "generated_at_kst": "2026-09-12 07:30 KST",
            "market": {"regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2}, "liquidity": {}},
            "recommendations": [], "news_issues": [], "upcoming_events": [],
        }
        stocks = {"us": {"market_name": "미국주식", "regime": "상승", "market_score": 80,
                         "recommendations": [{"name": "애플", "symbol": "AAPL", "score": 82, "decision": "분할매수 후보", "rsi": 58, "return_30d": 9}]},
                  "kr": {"market_name": "국내주식", "warnings": ["설정 필요"], "recommendations": []}}
        stocks["_mail"] = {"selected_sector_labels": ["반도체"], "holding_counts": {"us": 2, "kr": 1}, "news_issues": [{"title": "엔비디아 신제품", "url": "https://example.com", "source": "테스트", "impact": "호재 가능", "published_at_kst": "09-15 07:00", "related_holdings": ["NVDA"], "related_sectors": ["반도체"]}]}
        result = build_stock_email_html(stocks)
        self.assertIn("미국주식 추천", result)
        self.assertIn("애플", result)
        self.assertIn("국내주식", result)
        self.assertIn("PERSONAL STOCK DESK", result)
        self.assertIn("맞춤 주식 브리핑", result)
        self.assertIn("엔비디아 신제품", result)
        self.assertIn("반도체", result)
        self.assertEqual(stock_email_subject(stocks, True), "[테스트] 맞춤 주식 브리핑")

    def test_stock_email_contains_kis_positions_and_changes(self):
        stocks = {"us": {"market_name": "미국주식", "recommendations": [], "warnings": []}, "kr": {"market_name": "국내주식", "recommendations": [], "warnings": []}}
        stocks["_mail"] = {"portfolio": {"synced_at": "2026-09-17T07:30:00+09:00", "positions": [{"market": "kr", "symbol": "005930", "name": "삼성전자", "quantity": 10, "current_price": 81000, "daily_change_rate": 1.25, "evaluation_amount": 800000, "profit_loss": 50000, "profit_rate": 6.67, "currency": "KRW"}], "changes": {"baseline_at": "2026-09-16T07:30:00+09:00", "added": [{"market": "kr", "symbol": "005930", "name": "삼성전자"}], "removed": [], "quantity_changes": []}}}
        result = build_stock_email_html(stocks)
        self.assertIn("내 한국투자증권 계좌", result)
        self.assertIn("신규 삼성전자", result)
        self.assertIn("800,000.00", result)
        self.assertIn("일간 +1.25%", result)

    @patch.dict("os.environ", {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465", "SMTP_USERNAME": "sender@example.com", "SMTP_PASSWORD": "secret", "EMAIL_TO": "coin@example.com", "STOCK_EMAIL_TO": "stock@example.com"}, clear=True)
    @patch("src.email_report.smtplib.SMTP_SSL")
    def test_coin_and_stock_reports_use_separate_recipients(self, smtp_ssl):
        report = {"generated_at_kst": "2026-09-15 07:30 KST", "market": {"regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2}, "liquidity": {}}, "recommendations": [], "news_issues": [], "upcoming_events": []}
        stocks = {"us": {"generated_at_kst": "2026-09-15 07:30 KST", "market_name": "미국주식", "recommendations": [], "warnings": []}, "kr": {"market_name": "국내주식", "recommendations": [], "warnings": []}, "_mail": {}}
        self.assertTrue(send_email(report, stocks))
        messages = [call.args[0] for call in smtp_ssl.return_value.__enter__.return_value.send_message.call_args_list]
        self.assertEqual([message["To"] for message in messages], ["coin@example.com", "stock@example.com"])
        self.assertIn("코인 분석", messages[0]["Subject"])
        self.assertIn("맞춤 주식 브리핑", messages[1]["Subject"])

    @patch.dict("os.environ", {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465", "SMTP_USERNAME": "sender@example.com", "SMTP_PASSWORD": "secret", "EMAIL_TO": "coin-only@example.com"}, clear=True)
    @patch("src.email_report.smtplib.SMTP_SSL")
    def test_stock_report_never_falls_back_to_coin_recipient(self, smtp_ssl):
        report = {"generated_at_kst": "2026-09-16 07:30 KST", "market": {"regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2}, "liquidity": {}}, "recommendations": [], "news_issues": [], "upcoming_events": []}
        stocks = {"us": {"generated_at_kst": "2026-09-16 07:30 KST", "market_name": "미국주식", "recommendations": [], "warnings": []}, "kr": {"market_name": "국내주식", "recommendations": [], "warnings": []}, "_mail": {}}
        self.assertTrue(send_email(report, stocks))
        messages = [call.args[0] for call in smtp_ssl.return_value.__enter__.return_value.send_message.call_args_list]
        self.assertEqual([message["To"] for message in messages], ["coin-only@example.com"])
        self.assertIn("코인 분석", messages[0]["Subject"])

    @patch.dict("os.environ", {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465", "SMTP_USERNAME": "sender@example.com", "SMTP_PASSWORD": "secret", "EMAIL_TO": "coin@example.com", "STOCK_EMAIL_TO": "global@example.com", "MEMBER_STOCK_EMAIL_TO": "owner@example.com"}, clear=True)
    @patch("src.email_report.smtplib.SMTP_SSL")
    def test_member_stock_recipient_overrides_global_list(self, smtp_ssl):
        report = {"generated_at_kst": "2026-09-17 07:30 KST", "market": {"regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2}, "liquidity": {}}, "recommendations": [], "news_issues": [], "upcoming_events": []}
        stocks = {"us": {"generated_at_kst": "2026-09-17 07:30 KST", "market_name": "미국주식", "recommendations": [], "warnings": []}, "kr": {"market_name": "국내주식", "recommendations": [], "warnings": []}, "_mail": {}}
        self.assertTrue(send_email(report, stocks))
        messages = [call.args[0] for call in smtp_ssl.return_value.__enter__.return_value.send_message.call_args_list]
        self.assertEqual(messages[1]["To"], "owner@example.com")

    @patch.dict("os.environ", {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465", "SMTP_USERNAME": "sender@example.com", "SMTP_PASSWORD": "secret", "EMAIL_TO": "coin@example.com", "MEMBER_STOCK_EMAIL_TO": "owner@example.com", "EMAIL_REPORT_SCOPE": "stock", "TEST_EMAIL": "true"}, clear=True)
    @patch("src.email_report.smtplib.SMTP_SSL")
    def test_stock_only_scope_never_sends_coin_email(self, smtp_ssl):
        report = {"generated_at_kst": "2026-09-17 14:00 KST", "market": {"regime": "중립", "score": 50, "bitcoin": {"price": 100, "mvrv_z": 1.2}, "liquidity": {}}, "recommendations": [], "news_issues": [], "upcoming_events": []}
        stocks = {"us": {"market_name": "미국주식", "recommendations": [], "warnings": []}, "kr": {"market_name": "국내주식", "recommendations": [], "warnings": []}, "_mail": {}}
        self.assertTrue(send_email(report, stocks))
        messages = [call.args[0] for call in smtp_ssl.return_value.__enter__.return_value.send_message.call_args_list]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["To"], "owner@example.com")
        self.assertEqual(messages[0]["Subject"], "[테스트] 맞춤 주식 브리핑")


if __name__ == "__main__":
    unittest.main()
