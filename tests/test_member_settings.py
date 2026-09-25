from pathlib import Path
import unittest

from scripts.load_member_settings import env_block, valid_recipients


ROOT = Path(__file__).parents[1]


class MemberSettingsTests(unittest.TestCase):
    def test_recipient_validation_and_env_block(self):
        self.assertTrue(valid_recipients("one@example.com\ntwo@example.com"))
        self.assertFalse(valid_recipients("not-an-email"))
        self.assertIn("MEMBER_COIN_EMAIL_TO<<", env_block("MEMBER_COIN_EMAIL_TO", "one@example.com"))

    def test_workflows_load_browser_settings(self):
        for name in ("daily-email.yml", "analyze-and-deploy.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("python scripts/load_member_settings.py", workflow)
        validator = (ROOT / "scripts/validate_email_config.py").read_text(encoding="utf-8")
        self.assertIn("MEMBER_COIN_EMAIL_TO", validator)


if __name__ == "__main__":
    unittest.main()
