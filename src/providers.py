from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DataProviderError(RuntimeError):
    pass


class MarketDataClient:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"User-Agent": "coin-recomand/1.0 (market research; GitHub Actions)"})

    def _json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def upbit_markets(self) -> list[dict[str, Any]]:
        data = self._json("https://api.upbit.com/v1/market/all", params={"isDetails": "false"})
        return [item for item in data if item.get("market", "").startswith("KRW-")]

    def upbit_tickers(self, markets: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for start in range(0, len(markets), 50):
            results.extend(self._json("https://api.upbit.com/v1/ticker", params={"markets": ",".join(markets[start : start + 50])}))
            time.sleep(0.12)
        return results

    def upbit_daily_candles(self, market: str, count: int = 120) -> list[dict[str, Any]]:
        data = self._json("https://api.upbit.com/v1/candles/days", params={"market": market, "count": min(count, 200)})
        return list(reversed(data))

    def fear_and_greed(self) -> dict[str, Any]:
        data = self._json("https://api.alternative.me/fng/", params={"limit": 2, "format": "json"})
        latest = data["data"][0]
        return {
            "value": int(latest["value"]),
            "classification": latest["value_classification"],
            "previous": int(data["data"][1]["value"]) if len(data["data"]) > 1 else None,
        }

    def coingecko_trending(self) -> dict[str, int]:
        headers: dict[str, str] = {}
        key = os.getenv("COINGECKO_API_KEY", "").strip()
        if key:
            headers["x-cg-demo-api-key"] = key
        data = self._json("https://api.coingecko.com/api/v3/search/trending", headers=headers)
        return {item["item"]["symbol"].upper(): index + 1 for index, item in enumerate(data.get("coins", []))}

    def coinmetrics_mvrv_inputs(self) -> tuple[list[float], list[float]]:
        url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        params: dict[str, Any] | None = {
            "assets": "btc",
            "metrics": "CapMrktCurUSD,CapRealUSD",
            "frequency": "1d",
            "start_time": "2010-01-01",
            "page_size": 10000,
        }
        market_caps: list[float] = []
        realized_caps: list[float] = []
        while url:
            data = self._json(url, params=params)
            params = None
            for row in data.get("data", []):
                market = row.get("CapMrktCurUSD")
                realized = row.get("CapRealUSD")
                if market is not None and realized is not None:
                    market_caps.append(float(market))
                    realized_caps.append(float(realized))
            url = data.get("next_page_url")
        if not market_caps:
            raise DataProviderError("Coin Metrics에서 MVRV 계산 데이터를 받지 못했습니다.")
        return market_caps, realized_caps

    def bitcoin_mvrv_z(self) -> float:
        glassnode_key = os.getenv("GLASSNODE_API_KEY", "").strip()
        if glassnode_key:
            now = int(datetime.now(timezone.utc).timestamp())
            data = self._json(
                "https://api.glassnode.com/v1/metrics/market/mvrv_z_score",
                params={"a": "BTC", "i": "24h", "s": now - 259200, "u": now, "api_key": glassnode_key},
            )
            values = [float(row["v"]) for row in data if row.get("v") is not None]
            if values:
                return values[-1]
            raise DataProviderError("Glassnode MVRV Z-Score 응답이 비어 있습니다.")
        market_caps, realized_caps = self.coinmetrics_mvrv_inputs()
        from .indicators import mvrv_z_score

        value = mvrv_z_score(market_caps, realized_caps)
        if value is None:
            raise DataProviderError("MVRV Z-Score 계산에 필요한 이력이 부족합니다.")
        return value

    def reddit_mentions(self, aliases: dict[str, tuple[str, str]]) -> dict[str, int]:
        client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return {}
        token_response = self.session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            timeout=self.timeout,
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]
        posts = self._json(
            "https://oauth.reddit.com/r/CryptoCurrency/new",
            params={"limit": 100, "raw_json": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        cutoff = datetime.now(timezone.utc).timestamp() - 86400
        corpus = " ".join(
            f"{child['data'].get('title', '')} {child['data'].get('selftext', '')}"
            for child in posts.get("data", {}).get("children", [])
            if float(child.get("data", {}).get("created_utc", 0)) >= cutoff
        ).lower()
        result: dict[str, int] = {}
        for symbol, (english_name, korean_name) in aliases.items():
            patterns = [rf"(?<![a-z0-9])\${re.escape(symbol.lower())}(?![a-z0-9])", rf"\b{re.escape(english_name.lower())}\b"]
            if korean_name:
                patterns.append(re.escape(korean_name.lower()))
            result[symbol] = sum(len(re.findall(pattern, corpus, flags=re.IGNORECASE)) for pattern in patterns)
        return result
