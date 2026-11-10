import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import write_supabase_config as writer


class WriteSupabaseConfigTests(unittest.TestCase):
    def write(self, env, fetch):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True), \
                patch.object(writer, "_fetch_public_key", fetch), patch.object(writer, "Path") as path:
            target = Path(tmp) / "config.js"
            path.return_value = target
            writer.main()
            return target.read_text()

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
