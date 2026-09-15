from pathlib import Path
import unittest


class WorkflowScheduleTests(unittest.TestCase):
    def test_hourly_refresh_and_daily_email_are_separated(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/analyze-and-deploy.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 0-21,23 * * *"', workflow)
        self.assertIn('cron: "30 22 * * *"', workflow)
        self.assertIn("github.event.schedule == '30 22 * * *'", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.send_email", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("[send-test-email]", workflow)
        self.assertIn("STOCK_EMAIL_TO: ${{ secrets.STOCK_EMAIL_TO }}", workflow)
        self.assertIn("STOCK_HOLDINGS_US: ${{ secrets.STOCK_HOLDINGS_US }}", workflow)
        self.assertIn("STOCK_HOLDINGS_KR: ${{ secrets.STOCK_HOLDINGS_KR }}", workflow)
        self.assertIn("STOCK_SECTORS: ${{ secrets.STOCK_SECTORS }}", workflow)
        self.assertIn("SUPABASE_URL: ${{ secrets.SUPABASE_URL }}", workflow)
        self.assertIn("SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}", workflow)
        self.assertIn("python scripts/write_supabase_config.py", workflow)


if __name__ == "__main__":
    unittest.main()
