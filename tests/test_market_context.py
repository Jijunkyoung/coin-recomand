import os
import unittest
from unittest.mock import patch

from src.providers import MarketDataClient


class MarketContextTests(unittest.TestCase):
    @patch.dict(os.environ, {"CMC_API_KEY": "test-key"}, clear=False)
    def test_coinmarketcap_global_metrics_accepts_secret_alias(self):
        client = MarketDataClient()
        response = {
            "data": {
                "btc_dominance": 55.123,
                "eth_dominance": 12.456,
                "last_updated": "2026-09-11T00:00:00Z",
                "quote": {"USD": {"total_market_cap": 2_500_000_000_000, "total_volume_24h": 100_000_000_000, "altcoin_market_cap": 1_100_000_000_000}},
            }
        }
        with patch.object(client, "_json", return_value=response) as mocked:
            result = client.coinmarketcap_global_metrics()
        self.assertEqual(result["btc_dominance"], 55.12)
        self.assertEqual(result["total_market_cap_usd"], 2_500_000_000_000)
        self.assertEqual(mocked.call_args.kwargs["headers"]["X-CMC_PRO_API_KEY"], "test-key")

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
