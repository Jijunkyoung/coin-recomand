import unittest
from unittest.mock import patch

from src.providers import MarketDataClient


class NewsProviderTests(unittest.TestCase):
    def test_parses_deduplicates_and_classifies_news(self):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
          <item><title>비트코인 ETF 승인 기대 - 뉴스A</title><link>https://example.com/1</link><pubDate>Thu, 10 Sep 2026 22:00:00 GMT</pubDate><source>뉴스A</source></item>
          <item><title>비트코인 ETF 승인 기대 - 뉴스A</title><link>https://example.com/2</link><pubDate>Thu, 10 Sep 2026 21:50:00 GMT</pubDate><source>뉴스A</source></item>
          <item><title>거래소 해킹으로 코인 탈취 - 뉴스B</title><link>https://example.com/3</link><pubDate>Thu, 10 Sep 2026 21:00:00 GMT</pubDate><source>뉴스B</source></item>
          <item><title>글로벌 금 ETF에 자금 유입 - 코인매체</title><link>https://example.com/4</link><pubDate>Thu, 10 Sep 2026 20:00:00 GMT</pubDate><source>코인매체</source></item>
        </channel></rss>"""
        client = MarketDataClient()
        with patch.object(client, "_text", return_value=feed), patch("src.providers.datetime") as mocked_datetime:
            from datetime import datetime, timezone
            mocked_datetime.now.return_value = datetime(2026, 9, 10, 23, 0, tzinfo=timezone.utc)
            issues = client.crypto_news(["BTC"])
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]["category"], "ETF·기관")
        self.assertEqual(issues[0]["impact"], "호재 가능")
        self.assertEqual(issues[0]["related_symbols"], ["BTC"])
        self.assertEqual(issues[1]["category"], "보안")
        self.assertEqual(issues[1]["impact"], "악재 가능")


if __name__ == "__main__":
    unittest.main()
