import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts.append_owner_mail_recipient import append_recipient, run, select_recipient


RECIPIENT = "owner.work@example.com"
ENV = {"EMAIL_TO": RECIPIENT.upper() + ",coworker@example.com",
       "RECIPIENT_SHA256": hashlib.sha256(RECIPIENT.encode()).hexdigest()}


class AppendOwnerMailRecipientTests(unittest.TestCase):
    def test_selects_only_explicitly_confirmed_secret_recipient(self):
        self.assertEqual(select_recipient(ENV), RECIPIENT)
        with self.assertRaises(ValueError):
            select_recipient({**ENV, "EMAIL_TO": "coworker@example.com"})
        with self.assertRaises(ValueError):
            select_recipient({**ENV, "RECIPIENT_SHA256": ""})

    def test_preserves_existing_recipients_and_avoids_case_duplicates(self):
        self.assertEqual(append_recipient("first@example.com;second@example.com", RECIPIENT),
                         "first@example.com, second@example.com, " + RECIPIENT)
        self.assertEqual(append_recipient(RECIPIENT.upper(), RECIPIENT), RECIPIENT.upper())
        with self.assertRaises(ValueError):
            append_recipient("invalid", RECIPIENT)

    @patch("scripts.append_owner_mail_recipient.resolve_owner_id", return_value="sole-owner-id")
    @patch("scripts.append_owner_mail_recipient.request_json")
    def test_changes_only_mail_columns_on_bound_row_and_verifies_effective_settings(self, request, owner):
        original = {"coin_email": "personal@example.com, prior@example.com", "stock_email": None}
        expected = {"coin_email": original["coin_email"] + ", " + RECIPIENT,
                    "stock_email": "personal@example.com, " + RECIPIENT}
        request.side_effect = [[original], {"profile": {"stock_email": "personal@example.com"}},
                               [expected], {"profile": expected}]
        self.assertTrue(run(ENV))
        _, path, method, payload = request.call_args_list[2].args
        filters = parse_qs(urlsplit(path).query)
        self.assertEqual(method, "PATCH")
        self.assertEqual(payload, expected)
        self.assertEqual(filters["user_id"], ["eq.sole-owner-id"])
        self.assertEqual(filters["stock_email"], ["is.null"])
        self.assertEqual(filters["coin_email"], ['in.("personal@example.com, prior@example.com")'])
        self.assertNotIn("coworker@example.com", str(payload))

    @patch("scripts.append_owner_mail_recipient.resolve_owner_id", return_value="sole-owner-id")
    @patch("scripts.append_owner_mail_recipient.request_json")
    def test_repeated_run_does_not_write_and_concurrent_change_is_not_overwritten(self, request, owner):
        current = {"coin_email": RECIPIENT, "stock_email": RECIPIENT.upper()}
        request.side_effect = [[current], {"profile": current}, {"profile": current}]
        self.assertFalse(run(ENV))
        self.assertFalse(any(len(call.args) > 2 and call.args[2] == "PATCH" for call in request.call_args_list))
        request.reset_mock()
        current = {"coin_email": "personal@example.com", "stock_email": "personal@example.com"}
        request.side_effect = [[current], {"profile": current}, []]
        with self.assertRaisesRegex(RuntimeError, "concurrently"):
            run(ENV)

    @patch("scripts.append_owner_mail_recipient.resolve_owner_id", side_effect=RuntimeError("ambiguous owner"))
    @patch("scripts.append_owner_mail_recipient.request_json")
    def test_refuses_ambiguous_owner_without_reading_or_writing_preferences(self, request, owner):
        with self.assertRaisesRegex(RuntimeError, "ambiguous owner"):
            run(ENV)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
