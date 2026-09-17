import unittest

from scripts.load_member_stock_profile import env_block, function_url, validate_profile


class MemberStockProfileTests(unittest.TestCase):
    def test_function_url(self):
        self.assertEqual(function_url("https://demo.supabase.co/"), "https://demo.supabase.co/functions/v1/kis-portfolio")

    def test_validates_owner_mail_and_positions(self):
        payload = {"positions": [], "mail_profile": {"stock_email": "owner@example.com", "sector_ids": ["energy"]}}
        self.assertEqual(validate_profile(payload)["sector_ids"], ["energy"])
        with self.assertRaisesRegex(ValueError, "메일 주소"):
            validate_profile({"positions": [], "mail_profile": {"stock_email": "bad"}})

    def test_github_env_uses_unique_multiline_delimiter(self):
        block = env_block("MEMBER_STOCK_HOLDINGS_KR", "005930|삼성전자\n000660|SK하이닉스")
        self.assertTrue(block.startswith("MEMBER_STOCK_HOLDINGS_KR<<EOF_"))
        self.assertIn("005930|삼성전자", block)


if __name__ == "__main__":
    unittest.main()
