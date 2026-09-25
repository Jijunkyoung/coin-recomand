import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.major_events import build_major_events, load_manual_events, negative_event_risk


class MajorEventTests(unittest.TestCase):
    NOW = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)

    def test_manual_event_is_normalized_with_dday_and_scenarios(self):
        events = build_major_events([], [], [{
            "id": "clarity-vote",
            "title": "미국 CLARITY 법안 표결",
            "date": "2026-09-16",
            "importance": "매우 높음",
            "status": "확인 필요",
            "related_symbols": ["btc", "ETH"],
            "source": "Congress.gov",
        }], now=self.NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["days_until"], 2)
        self.assertEqual(events[0]["event_type"], "법안·규제")
        self.assertEqual(events[0]["related_symbols"], ["BTC", "ETH"])
        self.assertTrue(events[0]["bull_case"])
        self.assertTrue(events[0]["bear_case"])

    def test_news_weekday_candidate_requires_verification(self):
        events = build_major_events([], [{
            "title": "이번 주 수요일 CLARITY 법안 표결 예정",
            "source": "테스트 뉴스",
            "url": "https://example.com/clarity",
        }], [], now=self.NOW)
        self.assertEqual(events[0]["date"], "2026-09-16")
        self.assertEqual(events[0]["status"], "확인 필요")
        self.assertEqual(events[0]["origin"], "news")

    def test_official_policy_news_without_schedule_is_included(self):
        events = build_major_events([], [{
            "title": "금융위원회 가상자산 규제 지침 발표",
            "source": "금융위원회",
            "url": "https://example.com/fsc",
            "published_at": "2026-09-13T01:00:00+00:00",
            "official_source": True,
            "status": "발표",
        }], [], now=self.NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["origin"], "official")
        self.assertEqual(events[0]["event_kind"], "정부 발표")
        self.assertEqual(events[0]["importance"], "높음")
        self.assertEqual(events[0]["date"], "2026-09-13")

    def test_low_impact_event_and_expired_event_are_excluded(self):
        events = build_major_events(
            [{"title": "소규모 커뮤니티 AMA", "date": "2026-09-16"}],
            [],
            [{"title": "과거 FOMC", "date": "2026-09-01", "importance": "매우 높음"}],
            now=self.NOW,
        )
        self.assertEqual(events, [])

    def test_events_are_sorted_by_newest_date_with_unknown_dates_last(self):
        events = build_major_events([], [], [
            {"title": "날짜 미정 규제 일정", "importance": "매우 높음"},
            {"title": "먼저 예정된 FOMC", "date": "2026-09-16", "importance": "매우 높음"},
            {"title": "나중에 예정된 ETF 승인", "date": "2026-09-20", "importance": "높음"},
        ], now=self.NOW)
        self.assertEqual(
            [event["title"] for event in events],
            ["나중에 예정된 ETF 승인", "먼저 예정된 FOMC", "날짜 미정 규제 일정"],
        )

    def test_xrp_hack_news_is_marked_negative_and_penalized_once(self):
        title = "리플(XRP), 비트겟 해킹에 1억 290만 개 탈취…3억 5100만 달러 피해, 북한 라자루스 배후 의혹도"
        events = build_major_events([], [{
            "title": title, "source": "테스트 뉴스", "url": "https://example.com/xrp-hack",
            "published_at": "2026-09-14T01:00:00+00:00", "related_symbols": ["XRP"],
        }], [], now=self.NOW)
        self.assertEqual(events[0]["impact"], "악재 가능")
        self.assertEqual(events[0]["score_penalty"], 8)
        risk = negative_event_risk("XRP", [events[0], events[0]])
        self.assertEqual(risk["penalty"], 8)
        self.assertEqual(len(risk["events"]), 1)

    def test_positive_reversal_headline_overrides_crude_negative_keyword(self):
        events = build_major_events([], [{
            "title": "ETF 58억달러 순유출서 순유입으로 전환", "importance": "높음",
            "impact": "악재 가능", "published_at": "2026-09-14T01:00:00+00:00",
            "related_symbols": ["BTC"],
        }], [], now=self.NOW)
        self.assertEqual(events[0]["impact"], "호재 가능")
        self.assertEqual(events[0]["score_penalty"], 0)

        resilient = build_major_events([], [{
            "title": "비트겟 해킹에도 버틴 리플(XRP)…고래 4억7,000만개 매집에 상승세 이어가나",
            "importance": "높음", "impact": "악재 가능",
            "published_at": "2026-09-14T01:00:00+00:00", "related_symbols": ["XRP"],
        }], [], now=self.NOW)
        self.assertEqual(resilient[0]["impact"], "호재 가능")
        self.assertEqual(resilient[0]["score_penalty"], 0)

    def test_loads_versioned_manual_event_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text(json.dumps({"events": [{"title": "테스트 일정"}]}), encoding="utf-8")
            self.assertEqual(load_manual_events(path), [{"title": "테스트 일정"}])


if __name__ == "__main__":
    unittest.main()
