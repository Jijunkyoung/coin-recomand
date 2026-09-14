import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.major_events import build_major_events, load_manual_events


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

    def test_low_impact_event_and_expired_event_are_excluded(self):
        events = build_major_events(
            [{"title": "소규모 커뮤니티 AMA", "date": "2026-09-16"}],
            [],
            [{"title": "과거 FOMC", "date": "2026-09-01", "importance": "매우 높음"}],
            now=self.NOW,
        )
        self.assertEqual(events, [])

    def test_loads_versioned_manual_event_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text(json.dumps({"events": [{"title": "테스트 일정"}]}), encoding="utf-8")
            self.assertEqual(load_manual_events(path), [{"title": "테스트 일정"}])


if __name__ == "__main__":
    unittest.main()
