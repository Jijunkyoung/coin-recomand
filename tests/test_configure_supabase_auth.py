import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.configure_supabase_auth import build_payload, configure_auth


ENV = {
    "SUPABASE_PROJECT_REF": "project-ref",
    "SUPABASE_ACCESS_TOKEN": "management-token",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "465",
    "SMTP_USERNAME": "sender@example.com",
    "SMTP_PASSWORD": "app-password",
}


class ConfigureSupabaseAuthTests(unittest.TestCase):
    def test_payload_enables_confirmation_with_custom_smtp(self):
        payload = build_payload(ENV)

        self.assertTrue(payload["external_email_enabled"])
        self.assertFalse(payload["mailer_autoconfirm"])
        self.assertEqual(payload["smtp_admin_email"], "sender@example.com")
        self.assertEqual(payload["smtp_port"], 465)

    def test_rejects_invalid_port(self):
        with self.assertRaisesRegex(ValueError, "SMTP_PORT"):
            build_payload({**ENV, "SMTP_PORT": "invalid"})

    @patch("scripts.configure_supabase_auth.urlopen")
    def test_patches_project_auth_config(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = json.dumps(
            {"smtp_host": "smtp.example.com", "mailer_autoconfirm": False}
        ).encode("utf-8")
        mock_urlopen.return_value = response

        result = configure_auth(ENV)

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.method, "PATCH")
        self.assertEqual(
            request.full_url,
            "https://api.supabase.com/v1/projects/project-ref/config/auth",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer management-token")
        sent = json.loads(request.data)
        self.assertEqual(sent["smtp_pass"], "app-password")
        self.assertFalse(result["mailer_autoconfirm"])


if __name__ == "__main__":
    unittest.main()
