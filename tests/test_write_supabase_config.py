import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
from urllib.error import HTTPError

from scripts import write_supabase_config as writer


class WriteSupabaseConfigTests(unittest.TestCase):
    def write(self, env, fetch):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True), \
                patch.object(writer, "_fetch_public_key", fetch), patch.object(writer, "Path") as path, \
                patch.object(writer, "_validate_public_key") as validate:
            target = Path(tmp) / "config.js"
            path.return_value = target
            writer.main()
            validate.assert_called_once()
            return target.read_text()

    @patch.object(writer, "urlopen")
    def test_live_key_validation_rejects_401_without_writing_a_config(self, open_url):
        open_url.side_effect = HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO(b"private body"))
        with self.assertRaisesRegex(RuntimeError, "HTTP 401.*Replace SUPABASE_ANON_KEY") as caught:
            writer._validate_public_key(f"https://{writer.PROJECT_REF}.supabase.co", "sb_publishable_rejected")
        self.assertNotIn("sb_publishable_rejected", str(caught.exception))
        self.assertNotIn("private body", str(caught.exception))

    @patch.object(writer, "urlopen")
    def test_live_key_validation_checks_auth_settings_with_only_public_key(self, open_url):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"disable_signup":false}'
        open_url.return_value = response
        writer._validate_public_key(f"https://{writer.PROJECT_REF}.supabase.co", "sb_publishable_valid")
        request = open_url.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/auth/v1/settings"))
        self.assertEqual(request.get_header("Apikey"), "sb_publishable_valid")
        self.assertIsNone(request.get_header("Authorization"))

    def test_failed_validation_preserves_the_existing_published_config(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"SUPABASE_ANON_KEY": "sb_publishable_rejected"}, clear=True), \
                patch.object(writer, "_validate_public_key", side_effect=RuntimeError("rejected")), \
                patch.object(writer, "Path") as path:
            target = Path(tmp) / "config.js"
            target.write_text("existing verified login configuration")
            path.return_value = target
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                writer.main()
            self.assertEqual(target.read_text(), "existing verified login configuration")

    def test_expired_management_token_cannot_block_configured_publishable_key(self):
        with patch.object(writer, "_fetch_public_key", side_effect=AssertionError("must not call management")) as fetch:
            output = self.write({"SUPABASE_ANON_KEY": "sb_publishable_browser", "SUPABASE_ACCESS_TOKEN": "expired-secret"}, fetch)
            fetch.assert_not_called()
        self.assertIn("sb_publishable_browser", output)
        self.assertNotIn("expired-secret", output)

    def test_configured_legacy_anon_key_also_skips_management(self):
        payload = base64.urlsafe_b64encode(b'{"role":"anon"}').decode().rstrip("=")
        with patch.object(writer, "_fetch_public_key") as fetch:
            output = self.write({"SUPABASE_ANON_KEY": f"header.{payload}.signature", "SUPABASE_ACCESS_TOKEN": "expired"}, fetch)
            fetch.assert_not_called()
        self.assertIn(payload, output)

    def test_management_lookup_is_retained_only_for_missing_public_key(self):
        with patch.object(writer, "_fetch_public_key", return_value="sb_publishable_discovered") as fetch:
            output = self.write({"SUPABASE_ACCESS_TOKEN": "management-secret"}, fetch)
            fetch.assert_called_once_with(writer.PROJECT_REF, "management-secret")
        self.assertIn("sb_publishable_discovered", output)
        self.assertNotIn("management-secret", output)

    def test_management_401_has_actionable_error_without_response_body_or_token(self):
        error = HTTPError("https://api.supabase.com", 401, "Unauthorized", {}, io.BytesIO(b"private-body"))
        with patch.object(writer, "_fetch_public_key", side_effect=error) as fetch:
            with self.assertRaisesRegex(RuntimeError, "HTTP 401.*SUPABASE_ANON_KEY") as caught:
                self.write({"SUPABASE_ACCESS_TOKEN": "management-secret"}, fetch)
        self.assertNotIn("management-secret", str(caught.exception))
        self.assertNotIn("private-body", str(caught.exception))

    def test_privileged_or_invalid_configured_key_is_never_published(self):
        payload = base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip("=")
        for key in ("sb_secret_private", f"header.{payload}.signature", "invalid"):
            with patch.object(writer, "_fetch_public_key") as fetch, self.assertRaisesRegex(RuntimeError, "publishable"):
                self.write({"SUPABASE_ANON_KEY": key, "SUPABASE_ACCESS_TOKEN": "secret"}, fetch)
            fetch.assert_not_called()

    def test_url_must_be_exact_project_https_origin(self):
        host = f"{writer.PROJECT_REF}.supabase.co"
        for url in (f"https://{host}.evil.invalid", f"https://evil.invalid/{host}", f"http://{host}", f"https://{host}@evil.invalid", f"https://{host}/?key=private"):
            with patch.object(writer, "_fetch_public_key") as fetch, self.assertRaisesRegex(RuntimeError, "must target"):
                self.write({"SUPABASE_URL": url, "SUPABASE_ANON_KEY": "sb_publishable_browser"}, fetch)
            fetch.assert_not_called()

    def test_workflow_validates_login_before_analysis_and_email_generation(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/analyze-and-deploy.yml").read_text()
        self.assertLess(workflow.index("name: Configure member authentication"), workflow.index("name: Generate latest analysis"))


if __name__ == "__main__":
    unittest.main()
