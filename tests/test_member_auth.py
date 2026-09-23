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
            self.assertRegex(page, r'src="supabase-runtime-config\\.js\\?v=[^"]+"')
            self.assertRegex(page, r'src="auth\\.js\\?v=[^"]+"')
            self.assertIn('href="auth.css"', page)

    def test_auth_library_is_served_locally_and_signup_recovers_from_errors(self):
        for name in ("index.html", "us-stocks.html", "kr-stocks.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertRegex(page, r'src="vendor/supabase\\.min\\.js\\?v=[^"]+"')
            self.assertNotIn("cdn.jsdelivr.net/npm/@supabase", page)
        self.assertGreater((ROOT / "docs" / "vendor" / "supabase.min.js").stat().st_size, 100_000)
        script = (ROOT / "docs" / "auth.js").read_text(encoding="utf-8")
        self.assertIn("확인메일 전송 중", script)
        self.assertIn("finally{setBusy(form,false)}", script)
        self.assertIn("withTimeout", script)

    def test_logged_in_header_has_logout_action(self):
        script = (ROOT / "docs/auth.js").read_text(encoding="utf-8")
        self.assertIn('id="logoutTop"', script)
        self.assertIn('client.auth.signOut()', script)

    def test_coin_and_stock_recipient_lists_are_separate(self):
        auth = (ROOT / "docs/auth.js").read_text(encoding="utf-8")
        coin_page = (ROOT / "docs/app.js").read_text(encoding="utf-8")
        self.assertIn('id="profileCoinEmail"', auth)
        self.assertIn('id="profileStockEmail"', auth)
        self.assertIn('coin_email: parsed.valid.join("\\n")', coin_page)

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
            env = dict(
                os.environ,
                SUPABASE_PROJECT_REF="pgtxtnggjqaysjhtdepz",
                SUPABASE_URL="https://pgtxtnggjqaysjhtdepz.supabase.co",
                SUPABASE_ANON_KEY="sb_publishable_public-key",
            )
            subprocess.run(
                ["python", str(ROOT / "scripts/write_supabase_config.py")],
                cwd=directory,
                env=env,
                check=True,
            )
            output = (docs / "supabase-runtime-config.js").read_text(encoding="utf-8")
            self.assertIn("https://pgtxtnggjqaysjhtdepz.supabase.co", output)
            self.assertIn("sb_publishable_public-key", output)
            self.assertNotIn("service", output.lower())

    def test_kis_portfolio_is_owner_only_and_keeps_secrets_server_side(self):
        edge = (ROOT / "supabase" / "functions" / "kis-portfolio" / "index.ts").read_text(encoding="utf-8")
        browser = (ROOT / "docs" / "auth.js").read_text(encoding="utf-8")
        self.assertIn('env("KIS_OWNER_USER_ID")', edge)
        self.assertIn('env("KIS_OWNER_EMAIL")', edge)
        self.assertIn("user.id === ownerId", edge)
        self.assertIn("email === ownerEmail", edge)
        self.assertIn("ownerEmail ? email === ownerEmail", edge)
        self.assertIn('env("KIS_ACCOUNT_NO")', edge)
        self.assertIn('client.functions.invoke("kis-portfolio"', browser)
        self.assertNotIn("KIS_APP_SECRET", browser)
        self.assertNotIn("KIS_ACCOUNT_NO", browser)
        self.assertIn('env("KIS_SCHEDULER_KEY")', edge)
        self.assertIn('env("SUPABASE_SECRET_KEYS")', edge)
        self.assertIn('env("SUPABASE_SERVICE_ROLE_KEY")', edge)
        self.assertIn('request.headers.get("x-kis-scheduler-key")', edge)
        self.assertIn('request.headers.get("apikey")', edge)
        self.assertIn('requestApiKey === serverAdminKey', edge)
        self.assertIn('data.error_description || data.msg1 || data.error', edge)
        self.assertIn('한국투자증권 토큰 발급 실패:', edge)
        self.assertIn('if (!schedulerMode && !authorization.startsWith("Bearer "))', edge)
        self.assertIn("supabase.auth.getUser(accessToken)", edge)
        config = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("verify_jwt = false", config)

    def test_kis_snapshots_are_owner_only_and_used_for_changes(self):
        migration = (ROOT / "supabase" / "migrations" / "20260917_kis_portfolio_snapshots.sql").read_text(encoding="utf-8")
        edge = (ROOT / "supabase" / "functions" / "kis-portfolio" / "index.ts").read_text(encoding="utf-8")
        self.assertIn("enable row level security", migration.lower())
        self.assertIn("(select auth.uid()) = user_id", migration)
        self.assertIn('from("kis_portfolio_snapshots")', edge)
        self.assertIn("portfolioChanges", edge)
        self.assertIn("mail_profile", edge)

    def test_stock_pages_show_synced_account_portfolio(self):
        script = (ROOT / "docs" / "stock.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("kis-portfolio-sync"', script)
        self.assertIn("changes.quantity_changes", script)
        for name in ("us-stocks.html", "kr-stocks.html"):
            self.assertIn('id="accountPortfolio"', (ROOT / "docs" / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
