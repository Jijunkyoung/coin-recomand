import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
import requests

from src.stock_public_research import collect_macro, collect_public_research, parse_dart, parse_earnings, parse_filings, parse_fomc, parse_ics, parse_ipos

NOW = datetime(2026, 11, 25, 2, tzinfo=timezone.utc)


class PublicResearchTests(unittest.TestCase):
    def test_ics_timezone_dst_folded_lines_and_revisions(self):
        text = '''BEGIN:VEVENT
UID:a
SEQUENCE:1
DTSTART;TZID=US-Eastern:20261125T083000
SUMMARY:Gross Domestic Pro
 duct
END:VEVENT
BEGIN:VEVENT
UID:b
DTSTART:20261125T133000Z
SUMMARY:Other
END:VEVENT
BEGIN:VEVENT
UID:missing-zone
DTSTART:20261125T083000
SUMMARY:Do not guess
END:VEVENT'''
        rows = parse_ics(text, "test", "https://example.com", NOW)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["at"], "2026-11-25T13:30:00+00:00")
        self.assertEqual(rows[0]["title"], "미국 국내총생산(GDP)")
        summer = text.replace("20261125", "20260715")
        self.assertEqual(parse_ics(summer, "test", "https://example.com", datetime(2026, 7, 15, tzinfo=timezone.utc))[0]["at"], "2026-07-15T12:30:00+00:00")
        cancelled = text + '\nBEGIN:VEVENT\nUID:a\nSEQUENCE:2\nSTATUS:CANCELLED\nEND:VEVENT'
        self.assertEqual([x["id"] for x in parse_ics(cancelled, "test", "https://example.com", NOW)], ["test:b"])

    def test_fomc_does_not_invent_a_release_time(self):
        html = '<h4><a>2026 FOMC Meetings</a></h4><div class="fomc-meeting__month"><strong>December</strong></div><div class="fomc-meeting__date">8-9*</div>'
        row = parse_fomc(html, NOW)[0]
        self.assertEqual(row["date"], "2026-12-09")
        self.assertIsNone(row["at"])

    def test_earnings_distinguishes_estimate_and_prior_year_and_rejects_wrong_day(self):
        payload = {"data": {"asOf": "Wed, Nov 25, 2026", "rows": [{"symbol": "TEST", "name": "Test", "time": "time-pre-market", "epsForecast": "($0.09)", "lastYearEPS": "$1.20", "noOfEsts": "0"}]}}
        row = parse_earnings(payload, date(2026, 11, 25))[0]
        self.assertEqual(row["eps_estimate"], -.09)
        self.assertEqual(row["last_year_eps"], 1.2)
        self.assertEqual(row["estimates_count"], 0)
        self.assertNotIn("eps_actual", row)
        with self.assertRaises(ValueError): parse_earnings(payload, date(2026, 11, 26))

    def test_ipo_pricing_date_is_not_a_listing_date(self):
        row = parse_ipos({"data": {"priced": {"rows": [{"companyName": "Test", "pricedDate": "11/19/2026", "proposedSharePrice": "10.00"}]}}})[0]
        self.assertEqual(row["date_kind"], "공모가 확정일")
        self.assertEqual(row["status"], "공모가 확정")
        self.assertNotIn("listing_date", row)

    def test_sec_filings_require_valid_documents_and_recent_dates(self):
        recent = {"form": ["10-Q", "8-K", "10-K"], "filingDate": ["2026-11-19", "2026-11-20", "2025-01-01"], "accessionNumber": ["0000320193-26-000123"]*3,
                  "primaryDocument": ["aapl-20260926.htm", "../../unsafe.htm", "old.htm"], "reportDate": ["2026-09-26"]*3}
        rows = parse_filings({"cik": 320193, "filings": {"recent": recent}}, {"symbol": "AAPL", "name": "애플"}, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/aapl-20260926.htm")

    def test_dart_matches_publisher_not_subsidiary_or_mentioned_company(self):
        def item(creator, accession):
            return f'<item><title>(유가)삼성전자 - 공시</title><dc:creator>{creator}</dc:creator><dc:date>2026-11-25T00:00:00Z</dc:date><link>https://dart.fss.or.kr/api/link.jsp?rcpNo={accession}</link></item>'
        text = '<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>' + item('삼성전자', '20261125000001') + item('삼성전자서비스', '20261125000002') + '</channel></rss>'
        rows = parse_dart(text, {"kr": {"universe": [{"symbol": "005930", "name": "삼성전자"}]}}, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "005930")

    @patch("src.stock_public_research.fred_series")
    def test_rate_spread_requires_matching_observation_dates(self, fred):
        fred.return_value = [{"date": "2026-11-19", "value": 4.0}]
        reports = {"us": {"market_context": {"indicators": [{"id": "us10y", "date": "2026-11-18", "value": 5.0}]}}}
        rows = collect_macro(reports, NOW)
        self.assertIsNone(next(x for x in rows if x["id"] == "yield_spread")["value"])
        reports["us"]["market_context"]["indicators"][0]["date"] = "2026-11-19"
        self.assertEqual(next(x for x in collect_macro(reports, NOW) if x["id"] == "yield_spread")["value"], 1.0)

    @patch("src.stock_public_research.download", side_effect=requests.ConnectionError())
    def test_outage_preserves_schema_and_explicit_source_failures(self, download):
        result = collect_public_research({}, {"us": {"universe": []}, "kr": {"universe": []}}, NOW)
        self.assertEqual(result["earnings"], [])
        self.assertEqual(result["economic_events"], [])
        self.assertIn("미수집", result["sources"]["bls"]["status"])
        self.assertEqual(result["options"]["status"], "보류")


if __name__ == "__main__": unittest.main()
