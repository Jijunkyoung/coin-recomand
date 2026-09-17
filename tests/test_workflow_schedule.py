from pathlib import Path
import unittest


class WorkflowScheduleTests(unittest.TestCase):
    def test_hourly_refresh_also_recovers_daily_email(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/analyze-and-deploy.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 0-21,23 * * *"', workflow)
        self.assertIn('cron: "20 22 * * *"', workflow)
        self.assertNotIn('cron: "30 22 * * *"', workflow)
        self.assertIn("NOT_BEFORE_KST: \"07:20\"", workflow)
        self.assertIn("steps.delivery.outputs.should_send == 'true'", workflow)
        self.assertIn("[record-daily-email]", workflow)
        self.assertIn("FORCE_SEND: ${{ github.event_name == 'push' }}", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.send_email", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("[send-test-email]", workflow)
        self.assertIn("[send-stock-test-email]", workflow)
        self.assertIn("EMAIL_REPORT_SCOPE:", workflow)
        self.assertIn("[send-daily-email]", workflow)
        self.assertIn("STOCK_EMAIL_TO: ${{ secrets.STOCK_EMAIL_TO }}", workflow)
        self.assertIn("STOCK_HOLDINGS_US: ${{ secrets.STOCK_HOLDINGS_US }}", workflow)
        self.assertIn("STOCK_HOLDINGS_KR: ${{ secrets.STOCK_HOLDINGS_KR }}", workflow)
        self.assertIn("STOCK_SECTORS: ${{ secrets.STOCK_SECTORS }}", workflow)
        self.assertIn("SUPABASE_URL: ${{ secrets.SUPABASE_URL }}", workflow)
        self.assertIn("SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}", workflow)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}", workflow)
        self.assertIn("KIS_SCHEDULER_KEY: ${{ secrets.KIS_SCHEDULER_KEY }}", workflow)
        self.assertIn('REQUIRE_MEMBER_STOCK_PROFILE: "true"', workflow)
        self.assertIn("load_member_stock_profile.py", workflow)
        self.assertIn('REQUIRE_MEMBER_STOCK_PROFILE: "true"', workflow)
        self.assertIn("python scripts/write_supabase_config.py", workflow)

    def test_daily_email_has_fallback_and_never_cancels_delivery(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/daily-email.yml").read_text(encoding="utf-8")
        self.assertNotIn('cron: "20 22 * * *"', workflow)
        self.assertIn('cron: "50 22 * * *"', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("check_daily_email_delivery.py", workflow)
        self.assertIn("validate_email_config.py", workflow)
        self.assertIn("REQUIRE_EMAIL_DELIVERY: \"true\"", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("load_member_stock_profile.py", workflow)


if __name__ == "__main__":
    unittest.main()
