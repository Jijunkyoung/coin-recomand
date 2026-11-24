"""Public theme and screening data. Never reads or publishes account holdings."""
from __future__ import annotations

import hashlib
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

from .stock_sentiment import KST, number


def screening_metrics(history: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    valid = {}
    for row in history:
        try:
            day = datetime.strptime(str(row.get("date")), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        value = number(row.get("price"))
        if day <= now.astimezone(KST).date() and value is not None and value > 0:
            valid[day.isoformat()] = row
    rows = [valid[key] for key in sorted(valid)]
    prices = [float(row["price"]) for row in rows]
    result = {"date": rows[-1]["date"] if rows else None, "observations": len(rows),
              "sma50": None, "sma200": None, "high_52w": None, "low_52w": None,
              "position_52w": None, "drawdown_52w": None, "estimated_turnover": None}
    for period in (50, 200):
        if len(prices) >= period:
            result[f"sma{period}"] = statistics.mean(prices[-period:])
    for period in (5, 21, 63, 126, 252):
        result[f"return_{period}"] = (prices[-1] / prices[-period - 1] - 1) * 100 if len(prices) > period else None
    if len(prices) >= 252:
        high = max(number(row.get("high")) or float(row["price"]) for row in rows[-252:])
        low = min(number(row.get("low")) or float(row["price"]) for row in rows[-252:])
        result.update(high_52w=high, low_52w=low, drawdown_52w=(prices[-1] / high - 1) * 100,
                      position_52w=(prices[-1] - low) / (high - low) * 100 if high > low else None)
    if rows and number(rows[-1].get("volume")) is not None:
        result["estimated_turnover"] = prices[-1] * max(0, float(rows[-1]["volume"]))
    return result


def attach_themes(report: dict, settings: dict, news: list[dict], now: datetime | None = None) -> None:
    market = report["market"]
    definitions = settings.get("sectors", {})
    latest = (report.get("benchmark") or {}).get("history", [])
    date = latest[-1]["date"] if latest else None
    benchmark_return = number((report.get("benchmark") or {}).get("return_1d"))
    for stock in report.get("rankings", []):
        stock["screening"] = screening_metrics(stock.get("history", []), now)
        stock["sector_ids"] = [key for key, definition in definitions.items() if stock["symbol"] in definition.get(market, [])]
    themes = []
    for key, definition in definitions.items():
        expected = set(definition.get(market, []))
        if not expected:
            continue
        members = [row for row in report.get("rankings", []) if row["symbol"] in expected
                   and row["screening"]["date"] == date and number(row.get("return_1d")) is not None]
        change = statistics.mean(float(row["return_1d"]) for row in members) if members else None
        turnover = [row["screening"]["estimated_turnover"] for row in members
                    if row["screening"]["estimated_turnover"] is not None]
        leaders = sorted(members, key=lambda row: (-float(row["return_1d"]), row["symbol"]))[:3]
        total = sum(turnover) if turnover else None
        themes.append({"id": key, "label": definition["label"], "date": date, "count": len(members),
                       "expected_count": len(expected), "return_1d": change,
                       "relative": change - benchmark_return if change is not None and benchmark_return is not None else None,
                       "breadth": sum(float(row["return_1d"]) > 0 for row in members) / len(members) * 100 if members else None,
                       "estimated_turnover": total,
                       "turnover_coverage": len(turnover),
                       "concentration": max(turnover) / total * 100 if total else None,
                       "leaders": [{field: row.get(field) for field in ("symbol", "name", "price", "return_1d", "score")} for row in leaders]})
    themes.sort(key=lambda row: (row["return_1d"] is None, -(row["return_1d"] or 0), row["id"]))
    report["theme_board"] = {"themes": themes, "news": [row for row in news if row.get("market") == market and row["sector_id"] in {x["id"] for x in themes}],
                             "benchmark": (report.get("benchmark") or {}).get("name"),
                             "note": "설정된 분석종목 범위 · 같은 관측일의 일간 등락률 단순평균. 테마 간 종목 중복 가능. 거래대금은 종가×거래량 추정치이며 실제 체결대금이 아닙니다. 52주는 252개 일봉 기준입니다."}


def parse_theme_news(text: str, sector_id: str, label: str, now: datetime, market: str = "") -> list[dict]:
    rows, seen = [], set()
    for node in ET.fromstring(text).findall(".//item"):
        try:
            stamp = parsedate_to_datetime(node.findtext("pubDate") or "")
            if stamp.tzinfo is None:
                continue
            stamp = stamp.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        if not now - timedelta(hours=24) <= stamp <= now + timedelta(minutes=5):
            continue
        title, url = (node.findtext("title") or "").strip(), (node.findtext("link") or "").strip()
        if not title or not url.startswith("https://"):
            continue
        fingerprint = hashlib.sha256(re.sub(r"\W", "", title.lower()).encode()).hexdigest()[:20]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        source = (node.findtext("source") or "Yahoo Finance RSS").strip()
        rows.append({"id": fingerprint, "market": market, "sector_id": sector_id, "sector_label": label, "title": title,
                     "url": url, "source": source, "published_at": stamp.isoformat(), "verification": "언론 보도 · 원문 확인"})
    return sorted(rows, key=lambda row: row["published_at"], reverse=True)[:6]


def collect_theme_news(settings: dict, now: datetime | None = None) -> tuple[list[dict], list[str]]:
    now = now or datetime.now(timezone.utc)
    def fetch(item):
        key, definition, market = item
        # Use the publisher's independent RSS feed, split by market. Do not
        # retry or work around Google News' rate-limit response.
        symbols = definition.get(market, [])
        query = ",".join(symbol + (".KS" if market == "kr" else "") for symbol in symbols)
        response = requests.get("https://finance.yahoo.com/rss/headline", params={"s": query},
                                headers={"User-Agent": "coin-recomand/1.0"}, timeout=12)
        response.raise_for_status()
        return parse_theme_news(response.text, key, definition["label"], now, market)
    rows, warnings = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [(key, market, pool.submit(fetch, (key, value, market))) for key, value in settings.get("sectors", {}).items() for market in ("us", "kr") if value.get(market)]
        for key, market, future in pending:
            try:
                rows.extend(future.result())
            except (requests.RequestException, ValueError, ET.ParseError) as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                warnings.append(f"{'미국' if market == 'us' else '국내'} {settings['sectors'][key]['label']} 뉴스 미수집" + (f"(HTTP {status})" if status else ""))
    return sorted(rows, key=lambda row: row["published_at"], reverse=True), warnings
