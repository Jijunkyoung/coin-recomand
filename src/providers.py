from __future__ import annotations

import os
import re
import time
import html
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DataProviderError(RuntimeError):
    pass


def _link_titles(page: str, predicate: Any) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for href, body in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, flags=re.IGNORECASE | re.DOTALL):
        if not predicate(href) or href in seen:
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        text = " ".join(text.split())
        if len(text) >= 2:
            seen.add(href)
            titles.append(text)
    return titles


def _coinpan_post_id(href: str) -> str | None:
    parsed = urlparse(html.unescape(href))
    if parsed.fragment.lower().startswith("comment") or "comment_srl" in parse_qs(parsed.query):
        return None
    match = re.fullmatch(r"/free/(\d+)/?", parsed.path)
    if match:
        return match.group(1)
    document_ids = parse_qs(parsed.query).get("document_srl", [])
    if document_ids and document_ids[0].isdigit() and parse_qs(parsed.query).get("mid", ["free"])[0] == "free":
        return document_ids[0]
    return None


def _coinpan_posts(page: str) -> dict[str, str]:
    posts: dict[str, str] = {}
    for href, body in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, flags=re.IGNORECASE | re.DOTALL):
        post_id = _coinpan_post_id(href)
        if not post_id:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", " ", body))
        title = " ".join(title.split())
        if len(title) >= 2:
            posts.setdefault(post_id, title)
    return posts


def count_post_mentions(posts: list[str], aliases: dict[str, tuple[str, str]]) -> dict[str, int]:
    common_tickers = {"ONE", "GAS", "NEAR", "FLOW", "MASK", "LINK", "MOVE", "ME", "ID"}
    safe_short_tickers = {"BTC", "ETH", "XRP", "SOL", "ADA", "DOT", "TRX", "SUI", "TON"}
    result: dict[str, int] = {}
    for symbol, (english_name, korean_name) in aliases.items():
        patterns = [rf"(?<![a-z0-9])\${re.escape(symbol)}(?![a-z0-9])"]
        if (len(symbol) >= 4 and symbol not in common_tickers) or symbol in safe_short_tickers:
            patterns.append(rf"(?<![a-z0-9]){re.escape(symbol)}(?![a-z0-9])")
        if len(english_name.strip()) >= 4:
            patterns.append(rf"(?<![a-z0-9]){re.escape(english_name.strip())}(?![a-z0-9])")
        if len(korean_name.strip()) >= 2:
            patterns.append(re.escape(korean_name.strip()))
        result[symbol] = sum(1 for post in posts if any(re.search(pattern, post, flags=re.IGNORECASE) for pattern in patterns))
    return result


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

    def _text(self, url: str, *, params: dict[str, Any] | None = None) -> str:
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _coingecko_headers() -> dict[str, str]:
        key = os.getenv("COINGECKO_API_KEY", "").strip()
        return {"x-cg-demo-api-key": key} if key else {}

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
        data = self._json("https://api.coingecko.com/api/v3/search/trending", headers=self._coingecko_headers())
        return {item["item"]["symbol"].upper(): index + 1 for index, item in enumerate(data.get("coins", []))}

    def coingecko_coin_list(self) -> list[dict[str, Any]]:
        return self._json("https://api.coingecko.com/api/v3/coins/list", headers=self._coingecko_headers())

    def coingecko_coin_details(self, coin_id: str) -> dict[str, Any]:
        return self._json(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}",
            params={"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false", "developer_data": "false", "sparkline": "false"},
            headers=self._coingecko_headers(),
        )

    def github_repository_activity(self, repository_url: str) -> dict[str, Any]:
        parsed = urlparse(repository_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if parsed.netloc.lower() != "github.com" or len(parts) < 2:
            raise DataProviderError("GitHub 저장소 주소를 확인할 수 없습니다.")
        repository = f"{parts[0]}/{parts[1].removesuffix('.git')}"
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = os.getenv("GH_API_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        since = datetime.now(timezone.utc).timestamp() - 30 * 86400
        commits = self._json(
            f"https://api.github.com/repos/{repository}/commits",
            params={"since": datetime.fromtimestamp(since, timezone.utc).isoformat(), "per_page": 100},
            headers=headers,
        )
        latest_commit = None
        if commits:
            latest_commit = commits[0].get("commit", {}).get("committer", {}).get("date") or commits[0].get("commit", {}).get("author", {}).get("date")
        else:
            latest = self._json(f"https://api.github.com/repos/{repository}/commits", params={"per_page": 1}, headers=headers)
            if latest:
                latest_commit = latest[0].get("commit", {}).get("committer", {}).get("date") or latest[0].get("commit", {}).get("author", {}).get("date")
        latest_release = None
        try:
            release = self._json(f"https://api.github.com/repos/{repository}/releases/latest", headers=headers)
            latest_release = {"name": release.get("name") or release.get("tag_name"), "date": release.get("published_at")}
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
        return {"repository": repository, "commits_30d": len(commits), "latest_commit": latest_commit, "latest_release": latest_release}

    def github_project_activity(self, repository_urls: list[str]) -> dict[str, Any] | None:
        activities: list[dict[str, Any]] = []
        for repository_url in dict.fromkeys(repository_urls[:4]):
            try:
                activities.append(self.github_repository_activity(repository_url))
            except (DataProviderError, requests.RequestException):
                continue
        if not activities:
            return None

        def rank(activity: dict[str, Any]) -> tuple[int, int, float]:
            commits = int(activity.get("commits_30d") or 0)
            parsed = activity.get("latest_commit") or ""
            try:
                timestamp = datetime.fromisoformat(str(parsed).replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                timestamp = 0
            return (1 if commits else 0, commits, timestamp)

        return max(activities, key=rank)

    def mobula_metadata(self, asset: str) -> dict[str, Any] | None:
        key = os.getenv("MOBULA_API_KEY", "").strip()
        if not key:
            return None
        response = self._json(
            "https://api.mobula.io/api/1/metadata",
            params={"asset": asset},
            headers={"Authorization": key},
        )
        return response.get("data") if isinstance(response, dict) else None

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

    def reddit_mentions(self, aliases: dict[str, tuple[str, str]]) -> tuple[dict[str, int] | None, int]:
        client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return None, 0
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
        posts = [
            f"{child['data'].get('title', '')} {child['data'].get('selftext', '')}"
            for child in posts.get("data", {}).get("children", [])
            if float(child.get("data", {}).get("created_utc", 0)) >= cutoff
        ]
        return count_post_mentions(posts, aliases), len(posts)

    def dcinside_mentions(self, aliases: dict[str, tuple[str, str]], pages: int = 2) -> tuple[dict[str, int], int]:
        posts: list[str] = []
        for page in range(1, pages + 1):
            body = self._text("https://gall.dcinside.com/board/lists/", params={"id": "bitcoins_new1", "page": page})
            posts.extend(
                _link_titles(
                    body,
                    lambda href: "/board/view/" in href and "id=bitcoins_new1" in href and "t=cv" not in href and "no=1&" not in href,
                )
            )
            time.sleep(0.25)
        return count_post_mentions(posts, aliases), len(posts)

    def coinpan_mentions(self, aliases: dict[str, tuple[str, str]], pages: int = 2) -> tuple[dict[str, int], int]:
        posts: dict[str, str] = {}
        for page in range(1, pages + 1):
            try:
                body = self._text("https://coinpan.com/index.php", params={"mid": "free", "page": page, "m": 0})
            except requests.RequestException:
                body = self._text("https://coinpan.com/free", params={"page": page, "m": 1})
            posts.update(_coinpan_posts(body))
            time.sleep(0.25)
        titles = list(posts.values())
        if not titles:
            raise DataProviderError("코인판 게시글 주소를 찾지 못했습니다.")
        return count_post_mentions(titles, aliases), len(titles)
