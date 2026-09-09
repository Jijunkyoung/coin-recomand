import unittest
from datetime import datetime, timezone

from src.main import resolve_coingecko_id, summarize_unlock
from src.providers import MarketDataClient, _coinpan_posts, _link_titles, count_post_mentions
from src.scoring import alt_score


class CommunityAndEventTests(unittest.TestCase):
    def test_coingecko_override_resolves_renamed_pros_token(self):
        rows = [
            {"id": "prosper", "symbol": "pros", "name": "Prosper [OLD]"},
            {"id": "prosper-2", "symbol": "pros", "name": "Prosper"},
        ]
        self.assertEqual(resolve_coingecko_id(rows, "PROS", "Prosper", {"PROS": "prosper-2"}), "prosper-2")

    def test_counts_each_matching_post_once_and_avoids_common_ticker_noise(self):
        aliases = {"XRP": ("XRP", "리플"), "ONE": ("Harmony", "하모니")}
        posts = ["리플 XRP 오늘 강하네", "xrp 상승", "someone said this", "하모니 메인넷 업데이트"]
        result = count_post_mentions(posts, aliases)
        self.assertEqual(result["XRP"], 2)
        self.assertEqual(result["ONE"], 1)

    def test_extracts_only_selected_board_links(self):
        page = '<a href="/free/123">리플 소식</a><a href="/notice/1">공지</a><a href="/free/124#comment">2</a>'
        titles = _link_titles(page, lambda href: href.startswith("/free/") and "#comment" not in href)
        self.assertEqual(titles, ["리플 소식"])

    def test_coinpan_parser_supports_clean_and_query_urls_and_deduplicates(self):
        page = '''
            <a href="/free/123">리플 소식</a>
            <a href="https://coinpan.com/index.php?mid=free&document_srl=124">프로스퍼 진척</a>
            <a href="/free/123#comment">댓글 2</a>
            <a href="?mid=free&document_srl=124&comment_srl=9">댓글 링크</a>
        '''
        self.assertEqual(_coinpan_posts(page), {"123": "리플 소식", "124": "프로스퍼 진척"})

    def test_github_project_activity_chooses_active_repository(self):
        client = MarketDataClient()
        client.github_repository_activity = lambda url: {
            "repository": url,
            "commits_30d": 9 if url.endswith("active") else 0,
            "latest_commit": "2026-09-08T00:00:00Z" if url.endswith("active") else "2024-01-01T00:00:00Z",
        }
        result = client.github_project_activity(["https://github.com/example/old", "https://github.com/example/active"])
        self.assertEqual(result["repository"], "https://github.com/example/active")

    def test_summarizes_nearest_upcoming_unlock(self):
        metadata = {"release_schedule": [{"date": "2026-09-20T00:00:00Z", "amount": 5_000_000}, {"date": "2026-10-20T00:00:00Z", "amount": 1_000_000}]}
        result = summarize_unlock(metadata, 100_000_000, datetime(2026, 9, 9, tzinfo=timezone.utc))
        self.assertEqual(result["date"], "2026-09-20")
        self.assertEqual(result["percent_circulating"], 5.0)

    def test_large_near_unlock_outweighs_development_bonus(self):
        base = {"price": 120, "ema20": 110, "ema50": 100, "rsi": 55, "macd_histogram": 1, "return_7d": 5, "return_30d": 15, "volume_ratio": 1.2, "volatility": 60}
        active = {**base, "development": {"commits_30d": 30, "latest_commit_days": 1}}
        risky = {**active, "tokenomics": {"next_unlock": {"days_until": 10, "percent_circulating": 8}}}
        active_score, _, _ = alt_score(active, "상승")
        risky_score, _, risks = alt_score(risky, "상승")
        self.assertLess(risky_score, active_score)
        self.assertTrue(any("언락" in risk for risk in risks))


if __name__ == "__main__":
    unittest.main()
