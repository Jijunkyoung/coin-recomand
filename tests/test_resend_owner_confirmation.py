import json
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.resend_owner_confirmation import resend_confirmation


ENV = {
    "SUPABASE_URL": "https://project.supabase.co/",
    "SUPABASE_ANON_KEY": "public-key",
    "KIS_OWNER_EMAIL_CANDIDATE": "Owner@Example.com",
}


class ResendOwnerConfirmationTests(unittest.TestCase):
    @patch("scripts.resend_owner_confirmation.urlopen")
    def test_requests_signup_confirmation_for_owner(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = b"{}"
        mock_urlopen.return_value = response

        resend_confirmation(ENV)

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://project.supabase.co/auth/v1/resend")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["Apikey"], "public-key")
        body = json.loads(request.data)
        self.assertEqual(body["type"], "signup")
        self.assertEqual(body["email"], "owner@example.com")
        self.assertEqual(body["options"]["emailRedirectTo"], "https://jijunkyoung.github.io/coin-recomand/")

    @patch("scripts.resend_owner_confirmation._fetch_public_key", return_value="fresh-public-key")
    @patch("scripts.resend_owner_confirmation.urlopen")
    def test_prefers_current_project_key_from_management_api(self, mock_urlopen, mock_fetch_key):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = b"{}"
        mock_urlopen.return_value = response

        resend_confirmation(
            {
                **ENV,
                "SUPABASE_ACCESS_TOKEN": "management-token",
                "SUPABASE_PROJECT_REF": "project-ref",
            }
        )

        mock_fetch_key.assert_called_once_with("project-ref", "management-token")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.headers["Apikey"], "fresh-public-key")

    def test_rejects_multiple_owner_addresses(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            resend_confirmation({**ENV, "KIS_OWNER_EMAIL_CANDIDATE": "one@example.com,two@example.com"})

    @patch("scripts.resend_owner_confirmation.urlopen")
    def test_redacts_owner_address_from_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            "https://project.supabase.co/auth/v1/resend",
            500,
            "Server Error",
            {},
            BytesIO(b'{"message":"SMTP rejected Owner@Example.com"}'),
        )

        with self.assertRaises(RuntimeError) as caught:
            resend_confirmation(ENV)
        self.assertNotIn("Owner@Example.com", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
