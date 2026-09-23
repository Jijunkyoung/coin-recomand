import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.confirm_owner_user import confirm_owner


ENV = {
    "SUPABASE_URL": "https://project.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "server-secret",
    "KIS_OWNER_EMAIL_CANDIDATE": "Owner@Example.com",
}


def response(payload):
    item = MagicMock()
    item.__enter__.return_value = item
    item.__exit__.return_value = False
    item.read.return_value = json.dumps(payload).encode("utf-8")
    return item


class ConfirmOwnerUserTests(unittest.TestCase):
    @patch("scripts.confirm_owner_user.urlopen")
    def test_confirms_only_exact_owner_match(self, mock_urlopen):
        mock_urlopen.side_effect = [
            response({"users": [{"id": "owner-id", "email": "owner@example.com", "email_confirmed_at": None}, {"id": "other-id", "email": "other@example.com", "email_confirmed_at": None}]}),
            response({"id": "owner-id", "email": "owner@example.com", "email_confirmed_at": "2026-09-23T00:00:00Z"}),
        ]

        self.assertEqual(confirm_owner(ENV), "confirmed")

        update_request = mock_urlopen.call_args_list[1].args[0]
        self.assertEqual(update_request.method, "PUT")
        self.assertTrue(update_request.full_url.endswith("/auth/v1/admin/users/owner-id"))
        self.assertEqual(json.loads(update_request.data), {"email_confirm": True})

    @patch("scripts.confirm_owner_user.urlopen")
    def test_does_not_update_already_confirmed_owner(self, mock_urlopen):
        mock_urlopen.return_value = response({"users": [{"id": "owner-id", "email": "owner@example.com", "email_confirmed_at": "2026-09-23T00:00:00Z"}]})

        self.assertEqual(confirm_owner(ENV), "already-confirmed")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("scripts.confirm_owner_user.urlopen")
    def test_refuses_when_owner_account_does_not_exist(self, mock_urlopen):
        mock_urlopen.return_value = response({"users": [{"id": "other-id", "email": "other@example.com"}]})

        with self.assertRaisesRegex(RuntimeError, "found 0"):
            confirm_owner(ENV)

    @patch("scripts.confirm_owner_user.urlopen")
    def test_refuses_duplicate_owner_matches(self, mock_urlopen):
        mock_urlopen.return_value = response({"users": [{"id": "one", "email": "owner@example.com"}, {"id": "two", "email": "OWNER@example.com"}]})

        with self.assertRaisesRegex(RuntimeError, "found 2"):
            confirm_owner(ENV)


if __name__ == "__main__":
    unittest.main()
