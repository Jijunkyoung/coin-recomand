import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.bind_sole_owner import resolve_owner_id


ENV = {"SUPABASE_URL": "https://project.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "secret"}


def response(payload):
    item = MagicMock()
    item.__enter__.return_value = item
    item.__exit__.return_value = False
    item.read.return_value = json.dumps(payload).encode("utf-8")
    return item


class BindSoleOwnerTests(unittest.TestCase):
    @patch("scripts.bind_sole_owner.urlopen")
    def test_returns_only_confirmed_user_id(self, mock_urlopen):
        mock_urlopen.return_value = response({"users": [{
            "id": "owner-id", "email": "private@example.com", "email_confirmed_at": "2026-09-24T00:00:00Z",
        }]})
        self.assertEqual(resolve_owner_id(ENV), "owner-id")

    @patch("scripts.bind_sole_owner.urlopen")
    def test_refuses_multiple_users(self, mock_urlopen):
        mock_urlopen.return_value = response({"users": [
            {"id": "one", "email_confirmed_at": "2026-09-24T00:00:00Z"},
            {"id": "two", "email_confirmed_at": "2026-09-24T00:00:00Z"},
        ]})
        with self.assertRaisesRegex(RuntimeError, "exactly one confirmed account"):
            resolve_owner_id(ENV)

    @patch("scripts.bind_sole_owner.urlopen")
    def test_refuses_unconfirmed_user(self, mock_urlopen):
        mock_urlopen.return_value = response({"users": [{"id": "one", "email_confirmed_at": None}]})
        with self.assertRaisesRegex(RuntimeError, "confirmed users: 0"):
            resolve_owner_id(ENV)


if __name__ == "__main__":
    unittest.main()
