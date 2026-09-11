from pathlib import Path
import unittest


class WorkflowScheduleTests(unittest.TestCase):
    def test_hourly_refresh_and_daily_email_are_separated(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/analyze-and-deploy.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 0-21,23 * * *"', workflow)
        self.assertIn('cron: "30 22 * * *"', workflow)
        self.assertIn("github.event.schedule == '30 22 * * *'", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)


if __name__ == "__main__":
    unittest.main()
