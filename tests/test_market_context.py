import os
import unittest
from unittest.mock import patch

from src.providers import MarketDataClient


class MarketContextTests(unittest.TestCase):
    def test_fear_and_greed_returns_daily_history_in_date_order(self):
        client = MarketDataClient()
        response = {
            "data": [
                {"value": "62", "value_classification": "Greed", "timestamp": "1789052400"},
                {"value": "55", "value_classification": "Neutral", "timestamp": "1788966000"},
            ]
        }
        with patch.object(client, "_json", return_value=response) as mocked:
            result = client.fear_and_greed()
        self.assertEqual(result["value"], 62)
        self.assertEqual(result["previous"], 55)
        self.assertEqual([point["value"] for point in result["history"]], [55, 62])
        self.assertLess(result["history"][0]["date"], result["history"][1]["date"])
        self.assertEqual(mocked.call_args.kwargs["params"]["limit"], 30)

    @patch.dict(os.environ, {"COINMARKETCAL_API_KEY": "test-key"}, clear=False)
    def test_coinmarketcal_events_filters_related_coins(self):
        client = MarketDataClient()
        response = {
            "data": [
                {"id": "1", "title": "XRP Upgrade", "date": "2026-09-13T00:00:00Z", "coins": [{"symbol": "XRP"}]},
                {"id": "2", "title": "ADA Event", "date": "2026-09-14T00:00:00Z", "coins": [{"symbol": "ADA"}]},
            ]
        }
        with patch.object(client, "_json", return_value=response) as mocked:
            from datetime import datetime, timezone
            result = client.coinmarketcal_events(["BTC", "XRP"], now=datetime(2026, 9, 11, tzinfo=timezone.utc))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["related_symbols"], ["XRP"])
        self.assertEqual(mocked.call_args.kwargs["headers"]["x-api-key"], "test-key")

    def test_defillama_market_liquidity_calculates_seven_day_change(self):
        client = MarketDataClient()
        tvl = [{"date": "100000", "tvl": 100}, {"date": str(100000 + 7 * 86400), "tvl": 110}]
        stable = [
            {"date": "100000", "totalCirculatingUSD": {"peggedUSD": 200}},
            {"date": str(100000 + 7 * 86400), "totalCirculatingUSD": {"peggedUSD": 210}},
        ]
        with patch.object(client, "_json", side_effect=[tvl, stable]):
            result = client.defillama_market_liquidity()
        self.assertEqual(result["defi_tvl_change_7d"], 10.0)
        self.assertEqual(result["stablecoin_supply_change_7d"], 5.0)


if __name__ == "__main__":
    unittest.main()
