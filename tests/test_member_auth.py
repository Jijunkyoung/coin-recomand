import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).parents[1]


class MemberAuthTests(unittest.TestCase):
    def test_all_pages_load_shared_auth(self):
        for name in ("index.html", "us-stocks.html", "kr-stocks.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertRegex(page, r'src="supabase-runtime-config\.js\?v=[^"]+"')
            self.assertRegex(page, r'src="auth\.js\?v=[^"]+"')
            self.assertRegex(page, r'href="auth\.css(?:\?v=[^"]+)?"')

    def test_auth_library_is_served_locally_and_signup_recovers_from_errors(self):
        for name in ("index.html", "us-stocks.html", "kr-stocks.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertRegex(page, r'src="vendor/supabase\.min\.js\?v=[^"]+"')
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
        self.assertIn("GitHub Actions 설정 없이", coin_page)
        self.assertNotIn("copyEmailSecret", coin_page)
        index = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        self.assertIn("저장하고 자동 적용", index)
        self.assertNotIn("settings/secrets/actions", index)

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
        self.assertIn("ownerId ? user.id === ownerId", edge)
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
        self.assertNotIn("user_id: userId, holdings_kr: holdingsKr", edge)
        self.assertIn('preferences?.holdings_us || ""', edge)
        self.assertNotIn("profile = { ...defaultProfile(), ...(profile || {}), holdings_us:", browser)
        config = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("verify_jwt = false", config)

    def test_upbit_portfolio_is_owner_only_and_secrets_stay_server_side(self):
        edge = (ROOT / "supabase/functions/upbit-portfolio/index.ts").read_text(encoding="utf-8")
        browser = (ROOT / "docs/auth.js").read_text(encoding="utf-8")
        self.assertIn('env("KIS_OWNER_USER_ID")', edge)
        self.assertIn("user.id === ownerId", edge)
        self.assertIn('env("UPBIT_ACCESS_KEY")', edge)
        self.assertIn('env("UPBIT_SECRET_KEY")', edge)
        self.assertIn('env("UPBIT_PROXY_URL")', edge)
        self.assertIn('client.functions.invoke("upbit-portfolio"', browser)
        self.assertNotIn("UPBIT_SECRET_KEY", browser)
        self.assertIn('id="upbitPortfolio"', (ROOT / "docs/index.html").read_text(encoding="utf-8"))
        self.assertIn('addEventListener("upbit-portfolio-sync"', (ROOT / "docs/app.js").read_text(encoding="utf-8"))

    def test_asset_rows_are_sorted_by_current_value(self):
        stock = (ROOT / "docs/stock.js").read_text(encoding="utf-8")
        coin = (ROOT / "docs/app.js").read_text(encoding="utf-8")
        self.assertIn("right.evaluation_amount", stock)
        self.assertIn("right.evaluation_amount", coin)

    def test_major_events_are_before_methodology(self):
        page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        self.assertLess(page.index('class="major-events-section"'), page.index('class="panel methodology-panel"'))

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
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertIn('id="accountPortfolio"', page)
            self.assertIn('id="manualPortfolio"', page)
        self.assertIn("renderManualHoldings", script)
        self.assertIn("일간 등락률", script)
        self.assertNotIn('if(settingsDialog.open)renderStockSettings()', script)
        self.assertIn("GitHub Actions 설정 없이", script)
        self.assertNotIn("copyStockEmail", script)
        self.assertNotIn("copyStockSectors", script)
        for name in ("us-stocks.html", "kr-stocks.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertIn("저장하고 자동 적용", page)
            self.assertNotIn("settings/secrets/actions", page)

    def test_toss_securities_is_server_side_and_merged_with_kis(self):
        edge = (ROOT / "supabase/functions/kis-portfolio/index.ts").read_text(encoding="utf-8")
        browser = (ROOT / "docs/auth.js").read_text(encoding="utf-8") + (ROOT / "docs/stock.js").read_text(encoding="utf-8")
        self.assertIn('env("TOSSINVEST_CLIENT_ID")', edge)
        self.assertIn('env("TOSSINVEST_CLIENT_SECRET")', edge)
        self.assertIn('"https://openapi.tossinvest.com/oauth2/token"', edge)
        self.assertIn('tossGet("/api/v1/accounts"', edge)
        self.assertIn('tossGet("/api/v1/holdings"', edge)
        self.assertIn('headers["X-Tossinvest-Account"]', edge)
        self.assertIn('broker: "toss"', edge)
        self.assertIn("positionKey", edge)
        self.assertIn("토스증권", browser)
        self.assertNotIn("TOSSINVEST_CLIENT_SECRET", browser)

    def test_daily_stock_history_is_owner_only(self):
        migration = (ROOT / "supabase/migrations/20260926_stock_portfolio_daily_snapshots.sql").read_text(encoding="utf-8")
        edge = (ROOT / "supabase/functions/kis-portfolio/index.ts").read_text(encoding="utf-8")
        self.assertIn("unique (user_id, snapshot_date)", migration)
        self.assertIn("enable row level security", migration.lower())
        self.assertIn("(select auth.uid()) = user_id", migration)
        self.assertIn("revoke all on table public.stock_portfolio_daily_snapshots from anon", migration)
        self.assertIn('.from("stock_portfolio_daily_snapshots")', edge)
        self.assertIn('onConflict: "user_id,snapshot_date"', edge)
        self.assertIn("history: (history || []).reverse()", edge)

    def test_excel_history_download_keeps_native_charts(self):
        exporter = (ROOT / "docs/portfolio-export.js").read_text(encoding="utf-8")
        template = ROOT / "docs/assets/stock-portfolio-history-template.xlsx"
        self.assertIn('stock-portfolio-history-${latest.snapshot_date}.xlsx', exporter)
        self.assertIn('xl/worksheets/sheet2.xml', exporter)
        self.assertIn('xl/worksheets/sheet3.xml', exporter)
        self.assertIn("latestTotals", exporter)
        self.assertGreater(template.stat().st_size, 50_000)
        with zipfile.ZipFile(template) as workbook:
            names = set(workbook.namelist())
            self.assertIn("xl/drawings/charts/chart1.xml", names)
            self.assertIn("xl/drawings/charts/chart2.xml", names)
        for name in ("us-stocks.html", "kr-stocks.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertIn('src="vendor/jszip.min.js', page)
            self.assertIn('src="portfolio-export.js', page)
        self.assertGreater((ROOT / "docs/vendor/jszip.min.js").stat().st_size, 50_000)

    def test_research_tab_is_next_to_coin(self):
        for name in ("index.html", "us-stocks.html", "kr-stocks.html", "research.html"):
            page = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertLess(page.index('href="index.html"'), page.index('href="research.html"'))
            self.assertLess(page.index('href="research.html"'), page.index('href="us-stocks.html"'))


if __name__ == "__main__":
    unittest.main()
