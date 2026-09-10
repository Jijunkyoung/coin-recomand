import unittest

from src.email_report import parse_recipients


class EmailReportTests(unittest.TestCase):
    def test_parses_multiple_recipient_formats_and_removes_duplicates(self):
        value = "first@example.com\nSECOND@example.com;first@example.com,third@example.com"
        self.assertEqual(parse_recipients(value), ["first@example.com", "SECOND@example.com", "third@example.com"])

    def test_rejects_invalid_recipient(self):
        with self.assertRaisesRegex(ValueError, "잘못된 수신 이메일 주소"):
            parse_recipients("valid@example.com,not-an-email")


if __name__ == "__main__":
    unittest.main()
