import unittest
from pathlib import Path

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

    def test_new_secret_key_is_sent_as_apikey_not_bearer_jwt(self):
        source = (Path(__file__).parents[1] / "scripts" / "load_member_stock_profile.py").read_text(encoding="utf-8")
        self.assertIn('"apikey": service_key', source)
        self.assertNotIn('"Authorization": f"Bearer {service_key}"', source)


if __name__ == "__main__":
    unittest.main()
