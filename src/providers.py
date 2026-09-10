from __future__ import annotations

import os
import re
import time
import html
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DataProviderError(RuntimeError):
    pass


KST = timezone(timedelta(hours=9))


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


def _today_link_titles(page: str, predicate: Any, now: datetime | None = None) -> list[str]:
    current_date = (now or datetime.now(KST)).astimezone(KST).date()
    titles: list[str] = []
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", page, flags=re.IGNORECASE | re.DOTALL):
        dates = re.findall(r"(?<!\d)((?:20)?\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)", row)
        if dates:
            year, month, day = dates[-1]
            year_number = int(year) if len(year) == 4 else 2000 + int(year)
            if (year_number, int(month), int(day)) != (current_date.year, current_date.month, current_date.day):
                continue
        elif not re.search(r"(?<!\d)[0-2]?\d:[0-5]\d(?!\d)", row):
            continue
        titles.extend(_link_titles(row, predicate))
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

    def _text(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
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

    def crypto_news(self, symbols: list[str] | None = None, limit: int = 7) -> list[dict[str, Any]]:
        """Collect and classify recent Korean crypto headlines without an API key."""
        symbol_terms = [symbol.upper() for symbol in (symbols or []) if re.fullmatch(r"[A-Z0-9]{2,10}", symbol.upper())]
        query = "(비트코인 OR 이더리움 OR 암호화폐 OR 가상자산 OR 코인"
        if symbol_terms:
            query += " OR " + " OR ".join(symbol_terms[:5])
        query += ") when:1d"
        body = self._text(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
        )
        root = ET.fromstring(body)
        now = datetime.now(timezone.utc)
        seen: set[str] = set()
        issues: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            raw_title = " ".join((item.findtext("title") or "").split())
            link = (item.findtext("link") or "").strip()
            source_node = item.find("source")
            source = " ".join(((source_node.text if source_node is not None else "") or "").split()) or "Google News"
            if not raw_title or not link:
                continue
            title = re.sub(rf"\s+-\s+{re.escape(source)}\s*$", "", raw_title, flags=re.IGNORECASE).strip()
            normalized = re.sub(r"[^0-9a-z가-힣]", "", title.lower())
            fingerprint = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
            if not normalized or fingerprint in seen:
                continue
            try:
                published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(timezone.utc)
            except (TypeError, ValueError):
                published = now
            if published < now - timedelta(hours=36):
                continue
            seen.add(fingerprint)
            combined = title.lower()
            categories = (
                ("보안", ("해킹", "해커", "탈취", "공격", "취약점", "exploit", "hack")),
                ("ETF·기관", ("etf", "기관", "현물", "펀드", "보유량")),
                ("규제", ("규제", "법안", "sec", "소송", "정부", "금지", "승인")),
                ("상장·거래", ("상장", "상장폐지", "거래지원", "거래소", "listing")),
                ("개발·사업", ("업그레이드", "메인넷", "파트너십", "출시", "개발", "투자 유치")),
                ("토크노믹스", ("언락", "락업", "소각", "발행", "unlock", "burn")),
            )
            category = next((name for name, words in categories if any(word in combined for word in words)), "시장")
            negative_words = ("해킹", "탈취", "공격", "취약점", "상장폐지", "소송", "금지", "급락", "폭락", "청산", "언락", "파산")
            positive_words = ("승인", "상장", "파트너십", "출시", "업그레이드", "투자 유치", "신고가", "급등", "소각")
            negative = sum(word in combined for word in negative_words)
            positive = sum(word in combined for word in positive_words)
            impact = "악재 가능" if negative > positive else "호재 가능" if positive > negative else "중립·혼재"
            related = [symbol for symbol in symbol_terms if re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", title, flags=re.IGNORECASE)]
            issues.append(
                {
                    "title": title[:220],
                    "source": source[:80],
                    "url": link,
                    "published_at": published.isoformat(),
                    "published_at_kst": published.astimezone(KST).strftime("%m-%d %H:%M"),
                    "category": category,
                    "impact": impact,
                    "related_symbols": related,
                }
            )
        issues.sort(key=lambda issue: issue["published_at"], reverse=True)
        selected: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        for issue in issues:
            if source_counts.get(issue["source"], 0) >= 2:
                continue
            selected.append(issue)
            source_counts[issue["source"]] = source_counts.get(issue["source"], 0) + 1
            if len(selected) >= limit:
                break
        return selected

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

    def blockchain_mvrv_z(self) -> float:
        params = {
            "timespan": "10years",
            "sampled": "true",
            "metadata": "false",
            "cors": "true",
            "format": "json",
        }
        mvrv_data = self._json("https://api.blockchain.info/charts/mvrv", params=params)
        market_data = self._json("https://api.blockchain.info/charts/market-cap", params=params)
        mvrv_values = [float(row["y"]) for row in mvrv_data.get("values", []) if row.get("y") is not None and float(row["y"]) > 0]
        market_caps = [float(row["y"]) for row in market_data.get("values", []) if row.get("y") is not None and float(row["y"]) > 0]
        if len(market_caps) < 30 or not mvrv_values:
            raise DataProviderError("Blockchain.com MVRV 계산 데이터가 부족합니다.")
        from .indicators import mvrv_z_score

        realized_cap = market_caps[-1] / mvrv_values[-1]
        value = mvrv_z_score(market_caps, [realized_cap])
        if value is None:
            raise DataProviderError("Blockchain.com 데이터로 MVRV Z-Score를 계산할 수 없습니다.")
        return value

    def bitcoin_mvrv_z(self) -> tuple[float, str]:
        glassnode_key = os.getenv("GLASSNODE_API_KEY", "").strip()
        if glassnode_key:
            try:
                now = int(datetime.now(timezone.utc).timestamp())
                data = self._json(
                    "https://api.glassnode.com/v1/metrics/market/mvrv_z_score",
                    params={"a": "BTC", "i": "24h", "s": now - 259200, "u": now, "api_key": glassnode_key},
                )
                values = [float(row["v"]) for row in data if row.get("v") is not None]
                if values:
                    return values[-1], "Glassnode"
            except (requests.RequestException, DataProviderError, TypeError, ValueError):
                pass
        return self.blockchain_mvrv_z(), "Blockchain.com 계산값"

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
        now_kst = datetime.now(KST)
        cutoff = now_kst.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
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
            page_posts = _today_link_titles(
                    body,
                    lambda href: "/board/view/" in href and "id=bitcoins_new1" in href and "t=cv" not in href and "no=1&" not in href,
                )
            posts.extend(page_posts)
            if page > 1 and not page_posts:
                break
            time.sleep(0.25)
        return count_post_mentions(posts, aliases), len(posts)

    def coinpan_mentions(self, aliases: dict[str, tuple[str, str]], pages: int = 2) -> tuple[dict[str, int], int]:
        posts: dict[str, str] = {}
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            "Referer": "https://coinpan.com/",
            "Cache-Control": "no-cache",
        }
        for page in range(1, pages + 1):
            page_posts: dict[str, str] = {}
            last_error: requests.RequestException | None = None
            successful_response = False
            attempts = (
                ("https://coinpan.com/free", {"page": page}),
                ("https://coinpan.com/index.php", {"mid": "free", "page": page}),
                ("https://coinpan.com/free", {"page": page, "m": 1}),
            )
            for url, params in attempts:
                try:
                    body = self._text(url, params=params, headers=browser_headers)
                except requests.RequestException as exc:
                    last_error = exc
                    continue
                successful_response = True
                today_rows = "".join(
                    row
                    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", body, flags=re.IGNORECASE | re.DOTALL)
                    if _today_link_titles(row, lambda href: _coinpan_post_id(href) is not None)
                )
                page_posts = _coinpan_posts(today_rows)
                if page_posts:
                    break
            if not page_posts and page == 1 and last_error is not None and not successful_response:
                raise last_error
            posts.update(page_posts)
            if page > 1 and not page_posts:
                break
            time.sleep(0.25)
        titles = list(posts.values())
        if not titles:
            raise DataProviderError("코인판 게시글 주소를 찾지 못했습니다.")
        return count_post_mentions(titles, aliases), len(titles)
