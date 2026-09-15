import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parents[1]


class MemberAuthTests(unittest.TestCase):
    def test_all_pages_load_shared_auth(self):
        for name in ("index.html", "us-stocks.html", "kr-stocks.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertIn('src="supabase-config.js"', page)
            self.assertIn('src="auth.js"', page)
            self.assertIn('href="auth.css"', page)

    def test_rls_is_limited_to_authenticated_owner(self):
        sql = (ROOT / "supabase/migrations/20260915_user_preferences.sql").read_text(encoding="utf-8")
        self.assertIn("enable row level security", sql.lower())
        self.assertIn("(select auth.uid()) = user_id", sql)
        self.assertIn("revoke all on table public.user_preferences from anon", sql)
        self.assertNotIn("service_role", (ROOT / "docs/auth.js").read_text(encoding="utf-8"))

    def test_config_writer_only_emits_public_values(self):
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / "docs"
            docs.mkdir()
            env = dict(os.environ, SUPABASE_URL="https://sample.supabase.co", SUPABASE_ANON_KEY="public-key")
            subprocess.run(
                ["python", str(ROOT / "scripts/write_supabase_config.py")],
                cwd=directory,
                env=env,
                check=True,
            )
            output = (docs / "supabase-config.js").read_text(encoding="utf-8")
            self.assertIn("https://sample.supabase.co", output)
            self.assertIn("public-key", output)
            self.assertNotIn("service", output.lower())


if __name__ == "__main__":
    unittest.main()
