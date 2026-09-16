from datetime import datetime, timezone
import unittest

from scripts.check_daily_email_delivery import has_active_marker, is_not_before_kst, marker_name


class DailyEmailDeliveryTests(unittest.TestCase):
    def test_marker_uses_korean_calendar_date(self):
        self.assertEqual(marker_name(datetime(2026, 9, 15, 23, 30, tzinfo=timezone.utc)), "daily-email-kst-2026-09-16")

    def test_only_matching_nonexpired_marker_blocks_fallback(self):
        name = "daily-email-kst-2026-09-16"
        self.assertTrue(has_active_marker({"artifacts": [{"name": name, "expired": False}]}, name))
        self.assertFalse(has_active_marker({"artifacts": [{"name": name, "expired": True}]}, name))
        self.assertFalse(has_active_marker({"artifacts": [{"name": "daily-email-kst-2026-09-15", "expired": False}]}, name))

    def test_korean_not_before_time(self):
        before = datetime(2026, 9, 16, 22, 19, tzinfo=timezone.utc)
        after = datetime(2026, 9, 16, 22, 20, tzinfo=timezone.utc)
        self.assertFalse(is_not_before_kst("07:20", before))
        self.assertTrue(is_not_before_kst("07:20", after))
        self.assertTrue(is_not_before_kst("", before))

    def test_invalid_not_before_time_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            is_not_before_kst("25:00")


if __name__ == "__main__":
    unittest.main()
