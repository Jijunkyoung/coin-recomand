import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.stock_reported_earnings import eps_comparison, parse_reported_earnings
from src.stock_public_research import collect_filings, download, request_timeout

NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)
STOCK = {"symbol": "TEST", "name": "Test"}
ACCESSION = "0000320193-26-000123"


def fact(start, end, value, filed="2026-11-01", accn=ACCESSION, form="10-Q"):
    return {"start": start, "end": end, "val": value, "filed": filed, "accn": accn, "form": form}


def payload():
    return {"cik": 320193, "facts": {"us-gaap": {
        "EarningsPerShareDiluted": {"units": {"USD/shares": [fact("2026-07-01","2026-09-30",2),fact("2025-07-01","2025-09-30",1)]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [fact("2026-07-01","2026-09-30",200),fact("2025-07-01","2025-09-30",100)]}}
    }}}


class ReportedEarningsTests(unittest.TestCase):
    def test_quarter_reports_actual_values_and_same_filing_comparison(self):
        row = parse_reported_earnings(payload(), STOCK, NOW, 320193)[0]
        self.assertEqual((row["period_type"],row["eps"],row["revenue"]), ("quarter",2,200))
        self.assertEqual((row["eps_yoy"],row["revenue_yoy"]), (100,100))
        self.assertEqual(row["basis"], "US-GAAP")
        self.assertNotIn("surprise", row)

    def test_half_year_ytd_is_not_a_quarter_or_mixed_with_quarter_eps(self):
        data = payload()
        data["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"] = [fact("2026-01-01","2026-09-30",999)]
        row = parse_reported_earnings(data, STOCK, NOW)[0]
        self.assertEqual(row["eps"], 2)
        self.assertIsNone(row["revenue"])

    def test_annual_eps_does_not_generate_an_imaginary_fourth_quarter(self):
        data = payload()
        gaap = data["facts"]["us-gaap"]
        gaap["EarningsPerShareDiluted"]["units"]["USD/shares"] = [fact("2025-10-01","2026-09-30",8,form="10-K"), fact("2024-10-01","2025-09-30",6,form="10-K")]
        gaap["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"] = []
        rows = parse_reported_earnings(data, STOCK, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["period_type"], "annual")
        self.assertEqual(rows[0]["eps"], 8)

    def test_future_filings_are_excluded_and_latest_valid_restatement_wins(self):
        data = payload()
        rows = data["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"]
        rows += [fact("2026-07-01","2026-09-30",3,filed="2026-11-10"),fact("2026-07-01","2026-09-30",99,filed="2026-12-01")]
        self.assertEqual(parse_reported_earnings(data, STOCK, NOW)[0]["eps"], 3)

    def test_different_filing_prior_eps_is_not_silently_compared(self):
        data = payload()
        data["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"][1]["accn"] = "0000320193-25-000123"
        row = parse_reported_earnings(data, STOCK, NOW)[0]
        self.assertIsNone(row["previous_eps"])
        self.assertIsNone(row["eps_yoy"])

    def test_zero_eps_is_valid_and_other_currency_is_not_mislabeled_usd(self):
        data = payload()
        data["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"][0]["val"] = 0
        revenue=data["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]
        revenue["EUR"] = revenue.pop("USD")
        row=parse_reported_earnings(data, STOCK, NOW)[0]
        self.assertEqual(row["eps"],0)
        self.assertIsNone(row["revenue"])

    def test_negative_or_zero_base_eps_has_no_misleading_growth_percentage(self):
        self.assertEqual(eps_comparison(1,-1),(None,"흑자전환"))
        self.assertEqual(eps_comparison(-1,-2),(None,"적자축소"))
        self.assertEqual(eps_comparison(-3,-2),(None,"적자확대"))
        self.assertEqual(eps_comparison(-1,2),(None,"적자전환"))
        self.assertIsNone(eps_comparison(1,0)[0])

    def test_identity_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):parse_reported_earnings(payload(), STOCK, NOW, 9999)

    @patch("src.stock_public_research.download")
    def test_known_cik_does_not_depend_on_web_ticker_list(self, get):
        get.return_value={"cik":320193,"tickers":["TEST"],"filings":{"recent":{}}}
        rows, errors=collect_filings({"us":{"universe":[{**STOCK,"sec_cik":320193}]}},NOW)
        self.assertEqual(errors,[])
        self.assertEqual(get.call_count,1)
        self.assertEqual(get.call_args.args[0],"https://data.sec.gov/submissions/CIK0000320193.json")

    @patch("src.stock_public_research.requests.get")
    def test_numeric_string_provider_success_code_is_accepted(self, get):
        response=MagicMock();response.json.return_value={"status":{"rCode":"200"},"data":{}}
        get.return_value=response
        self.assertEqual(download("https://example.invalid",json=True)["status"]["rCode"],"200")

    def test_only_nasdaq_has_a_longer_bounded_timeout(self):
        self.assertEqual(request_timeout("https://api.nasdaq.com/api/calendar/earnings"),25)
        self.assertEqual(request_timeout("https://data.sec.gov/submissions/file.json"),12)
        self.assertEqual(request_timeout("https://api.nasdaq.com.example.invalid/"),12)


if __name__ == "__main__":unittest.main()
