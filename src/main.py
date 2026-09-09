from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .email_report import send_email
from .indicators import annualized_volatility, ema, macd, pct_change, rsi, volume_ratio
from .providers import MarketDataClient
from .scoring import alt_score, market_regime, recommendation_label

KST = timezone(timedelta(hours=9))


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _days_since(value: Any, now: datetime | None = None) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, (current - parsed).days)


def resolve_coingecko_id(rows: list[dict[str, Any]], symbol: str, english_name: str, overrides: dict[str, str] | None = None) -> str | None:
    override = (overrides or {}).get(symbol.upper())
    if override:
        return override
    matches = [row for row in rows if str(row.get("symbol", "")).upper() == symbol.upper()]
    normalized_name = re.sub(r"[^a-z0-9]", "", english_name.lower())
    for row in matches:
        candidate = re.sub(r"[^a-z0-9]", "", str(row.get("name", "")).lower())
        if candidate == normalized_name:
            return str(row["id"])
    return str(matches[0]["id"]) if len(matches) == 1 else None


def summarize_unlock(metadata: dict[str, Any] | None, circulating_supply: float | None, now: datetime | None = None) -> dict[str, Any] | None:
    if not metadata:
        return None
    schedule = metadata.get("release_schedule") or metadata.get("releaseSchedule") or []
    events: list[dict[str, Any]] = []
    if isinstance(schedule, list):
        events = [item for item in schedule if isinstance(item, dict)]
    elif isinstance(schedule, dict):
        for key, value in schedule.items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, dict):
                    event = dict(item)
                    event.setdefault("date", key)
                    events.append(event)
    current = now or datetime.now(timezone.utc)
    upcoming: list[tuple[datetime, dict[str, Any]]] = []
    for event in events:
        date = _parse_datetime(next((event.get(key) for key in ("date", "unlock_date", "release_date", "timestamp", "time") if event.get(key) is not None), None))
        if date and date >= current:
            upcoming.append((date, event))
    if not upcoming:
        return None
    date, event = min(upcoming, key=lambda item: item[0])
    amount_value = next((event.get(key) for key in ("amount", "token_amount", "tokens", "quantity", "value") if event.get(key) is not None), None)
    try:
        amount = float(amount_value) if amount_value is not None else None
    except (TypeError, ValueError):
        amount = None
    percent = amount / circulating_supply * 100 if amount is not None and circulating_supply else None
    if percent is None:
        percent_value = next((event.get(key) for key in ("percent_circulating", "percentage", "percent", "unlock_percentage") if event.get(key) is not None), None)
        try:
            percent = float(percent_value) if percent_value is not None else None
            if percent is not None and 0 < percent <= 1:
                percent *= 100
        except (TypeError, ValueError):
            percent = None
    return {
        "date": date.date().isoformat(),
        "days_until": max(0, (date - current).days),
        "amount": round(amount, 4) if amount is not None else None,
        "percent_circulating": round(percent, 2) if percent is not None else None,
    }


def project_context(details: dict[str, Any], activity: dict[str, Any] | None, unlock_metadata: dict[str, Any] | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    market_data = details.get("market_data") or {}
    circulating = market_data.get("circulating_supply")
    total = market_data.get("total_supply") or market_data.get("max_supply")
    circulating_ratio = float(circulating) / float(total) * 100 if circulating and total else None
    notice = details.get("public_notice") or ""
    notice = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(notice))).split())[:180]
    development: dict[str, Any] = {"status": "미수집"}
    if activity:
        commit_days = _days_since(activity.get("latest_commit"), now)
        release = activity.get("latest_release") or {}
        release_days = _days_since(release.get("date"), now)
        commits = activity.get("commits_30d")
        status = activity.get("status") or ("활발" if (commits or 0) >= 20 or (release_days is not None and release_days <= 30) else "진행 중" if (commits or 0) >= 5 else "정체 확인" if commit_days is not None and commit_days >= 120 else "낮은 활동")
        development = {
            **activity,
            "status": status,
            "latest_commit_days": commit_days,
            "latest_release_days": release_days,
            "latest_release_name": release.get("name"),
        }
    return {
        "development": development,
        "tokenomics": {
            "circulating_ratio": round(circulating_ratio, 2) if circulating_ratio is not None else None,
            "next_unlock": summarize_unlock(unlock_metadata, float(circulating) if circulating else None, now),
            "unlock_data_available": unlock_metadata is not None,
            "project_notice": notice or None,
        },
        "coingecko_id": details.get("id"),
    }


def technical_metrics(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < 60:
        raise ValueError("60일 이상 거래 이력이 필요합니다.")
    closes = [float(candle["trade_price"]) for candle in candles]
    volumes = [float(candle["candle_acc_trade_price"]) for candle in candles]
    macd_line, signal, histogram = macd(closes)
    return {
        "price": closes[-1],
        "ema20": round_or_none(ema(closes, 20)),
        "ema50": round_or_none(ema(closes, 50)),
        "rsi": round_or_none(rsi(closes)),
        "macd": round_or_none(macd_line),
        "macd_signal": round_or_none(signal),
        "macd_histogram": round_or_none(histogram),
        "return_7d": round_or_none(pct_change(closes, 7)),
        "return_30d": round_or_none(pct_change(closes, 30)),
        "volume_ratio": round_or_none(volume_ratio(volumes)),
        "volatility": round_or_none(annualized_volatility(closes)),
        "sparkline": [round(value, 4) for value in closes[-30:]],
        "history": [
            {
                "date": candle.get("candle_date_time_kst", candle.get("candle_date_time_utc", ""))[:10],
                "open": round(float(candle.get("opening_price", candle["trade_price"])), 4),
                "high": round(float(candle.get("high_price", candle["trade_price"])), 4),
                "low": round(float(candle.get("low_price", candle["trade_price"])), 4),
                "price": round(float(candle["trade_price"]), 4),
                "volume": round(float(candle["candle_acc_trade_price"])),
            }
            for candle in candles
        ],
    }


def load_settings(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(settings: dict[str, Any], client: MarketDataClient | None = None) -> dict[str, Any]:
    client = client or MarketDataClient()
    warnings: list[str] = []
    market_rows = client.upbit_markets()
    market_names = {row["market"]: row.get("korean_name") or row["market"] for row in market_rows}
    english_names = {row["market"]: row.get("english_name") or row["market"] for row in market_rows}
    tickers = client.upbit_tickers(list(market_names))
    tickers.sort(key=lambda row: float(row.get("acc_trade_price_24h") or 0), reverse=True)

    btc_candles = client.upbit_daily_candles("KRW-BTC", settings["upbit_candle_days"])
    bitcoin = technical_metrics(btc_candles)
    bitcoin["market"] = "KRW-BTC"
    try:
        bitcoin["mvrv_z"] = round_or_none(client.bitcoin_mvrv_z())
    except Exception as exc:
        bitcoin["mvrv_z"] = None
        hint = "GLASSNODE_API_KEY를 등록하면 공식 지표를 수집할 수 있습니다." if not os.getenv("GLASSNODE_API_KEY") else "등록한 Glassnode 키와 요금제 권한을 확인하세요."
        warnings.append(f"MVRV Z-Score 미수집: {type(exc).__name__}. {hint}")
    try:
        fear_greed = client.fear_and_greed()
        bitcoin["fear_greed"] = fear_greed["value"]
    except Exception as exc:
        fear_greed = {"value": None, "classification": "미수집", "previous": None}
        bitcoin["fear_greed"] = None
        warnings.append(f"공포·탐욕 지수 미수집: {type(exc).__name__}")
    market_score, regime, market_reasons = market_regime(bitcoin)

    try:
        trending = client.coingecko_trending()
    except Exception as exc:
        trending = {}
        warnings.append(f"CoinGecko 인기 검색 미수집: {type(exc).__name__}")

    excluded = set(settings["excluded_symbols"])
    candidates = [
        ticker
        for ticker in tickers
        if ticker["market"].split("-", 1)[1] not in excluded
        and float(ticker.get("acc_trade_price_24h") or 0) >= settings["minimum_24h_value_krw"]
    ][: settings["screen_count"]]
    aliases = {
        ticker["market"].split("-", 1)[1]: (english_names[ticker["market"]], market_names[ticker["market"]])
        for ticker in candidates
    }
    community_mentions: dict[str, dict[str, int] | None] = {}
    community_samples: dict[str, int] = {}
    community_collectors = {
        "reddit": lambda: client.reddit_mentions(aliases),
        "dcinside": lambda: client.dcinside_mentions(aliases, settings.get("community_pages", 2)),
        "coinpan": lambda: client.coinpan_mentions(aliases, settings.get("community_pages", 2)),
    }
    source_names = {"reddit": "Reddit", "dcinside": "디시인사이드", "coinpan": "코인판"}
    for source, collect in community_collectors.items():
        try:
            counts, sample_size = collect()
            community_mentions[source] = counts
            community_samples[source] = sample_size
        except Exception as exc:
            community_mentions[source] = None
            community_samples[source] = 0
            warnings.append(f"{source_names[source]} 언급 수 미수집: {type(exc).__name__}")

    analyzed: list[dict[str, Any]] = []
    for ticker in candidates:
        market = ticker["market"]
        symbol = market.split("-", 1)[1]
        try:
            metrics = technical_metrics(client.upbit_daily_candles(market, settings["upbit_candle_days"]))
            breakdown = {source: counts.get(symbol, 0) if counts is not None else None for source, counts in community_mentions.items()}
            available_sources = sum(1 for counts in community_mentions.values() if counts is not None)
            total_mentions = sum(value or 0 for value in breakdown.values())
            total_samples = sum(community_samples[source] for source, counts in community_mentions.items() if counts is not None)
            metrics.update(
                {
                    "trending_rank": trending.get(symbol),
                    "reddit_mentions": breakdown.get("reddit"),
                    "community_mentions": breakdown,
                    "community_total": total_mentions,
                    "community_sources": available_sources,
                    "community_sample_size": total_samples,
                    "community_exposure_rate": round(total_mentions / total_samples * 100, 2) if total_samples else None,
                    "trade_value_24h": round(float(ticker.get("acc_trade_price_24h") or 0)),
                }
            )
            score, reasons, risks = alt_score(metrics, regime)
            analyzed.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "name": market_names[market],
                    "english_name": english_names[market],
                    "score": score,
                    "decision": recommendation_label(score, regime),
                    "reasons": reasons[:6],
                    "risks": risks[:5],
                    **metrics,
                }
            )
        except Exception as exc:
            warnings.append(f"{market} 분석 제외: {type(exc).__name__}")
        time.sleep(0.12)
    analyzed.sort(key=lambda coin: (coin["score"], coin["trade_value_24h"]), reverse=True)
    enriched = analyzed[: settings.get("fundamental_candidate_count", 12)]
    try:
        coingecko_coins = client.coingecko_coin_list()
    except Exception as exc:
        coingecko_coins = []
        warnings.append(f"프로젝트·토크노믹스 정보 미수집: {type(exc).__name__}")
    if not os.getenv("MOBULA_API_KEY", "").strip():
        warnings.append("예정 토큰 언락 상세 미수집: MOBULA_API_KEY를 GitHub Secret에 등록하면 반영됩니다.")
    for coin in enriched:
        coin_id = resolve_coingecko_id(coingecko_coins, coin["symbol"], coin["english_name"], settings.get("coingecko_id_overrides"))
        if not coin_id:
            continue
        try:
            details = client.coingecko_coin_details(coin_id)
            repositories = ((details.get("links") or {}).get("repos_url") or {}).get("github") or []
            activity = None
            if repositories:
                try:
                    activity = client.github_project_activity(repositories)
                    if activity is None:
                        warnings.append(f"{coin['symbol']} 공개 GitHub 저장소 응답 없음")
                except Exception as exc:
                    warnings.append(f"{coin['symbol']} 개발 진척 미수집: {type(exc).__name__}")
            else:
                homepage = next((url for url in ((details.get("links") or {}).get("homepage") or []) if url), None)
                activity = {"status": "공개 GitHub 없음", "repository": None, "commits_30d": None, "latest_commit": None, "latest_release": None, "source_url": homepage}
            unlock_metadata = None
            if os.getenv("MOBULA_API_KEY", "").strip():
                try:
                    unlock_metadata = client.mobula_metadata(coin["english_name"])
                except Exception as exc:
                    warnings.append(f"{coin['symbol']} 언락 일정 미수집: {type(exc).__name__}")
            coin.update(project_context(details, activity, unlock_metadata))
            score, reasons, risks = alt_score(coin, regime)
            coin.update({"score": score, "decision": recommendation_label(score, regime), "reasons": reasons[:6], "risks": risks[:5]})
        except Exception as exc:
            warnings.append(f"{coin['symbol']} 프로젝트 정보 미수집: {type(exc).__name__}")
        time.sleep(0.8)
    enriched.sort(key=lambda coin: (coin["score"], coin["trade_value_24h"]), reverse=True)
    top = enriched[: settings["recommendation_count"]]
    now = datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "generated_at_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
        "market": {
            "score": market_score,
            "regime": regime,
            "reasons": market_reasons,
            "bitcoin": bitcoin,
            "fear_greed": fear_greed,
        },
        "recommendations": top,
        "screened": len(analyzed),
        "methodology": {
            "market": "BTC 추세·모멘텀·거래량·MVRV Z·공포탐욕 종합",
            "alt": "기술지표·거래량 + Reddit·디시·코인판 노출도 + 개발 진척·토큰 언락·희석 위험",
            "execution": "실제 주문 없음, 하락장 신규 매수 차단, 후보는 분할 접근 전제",
        },
        "data_quality": {"status": "주의" if warnings else "정상", "warnings": warnings},
        "sources": [
            {"name": "Upbit", "url": "https://global-docs.upbit.com/reference/list-tickers"},
            {"name": "Coin Metrics", "url": "https://docs.coinmetrics.io/api/v4"},
            {"name": "CoinGecko", "url": "https://docs.coingecko.com/docs/keyless-public-api"},
            {"name": "GitHub", "url": "https://docs.github.com/rest/commits/commits"},
            {"name": "Mobula", "url": "https://docs.mobula.io/guides/token-unlock"},
            {"name": "Reddit", "url": "https://www.reddit.com/r/CryptoCurrency/"},
            {"name": "DCInside", "url": "https://gall.dcinside.com/board/lists/?id=bitcoins_new1"},
            {"name": "Coinpan", "url": "https://coinpan.com/free"},
            {"name": "Alternative.me", "url": "https://alternative.me/crypto/fear-and-greed-index/"},
        ],
        "disclaimer": "정량 지표 기반 참고자료이며 투자 자문이나 수익 보장이 아닙니다. 실제 주문을 실행하지 않습니다.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="코인 시장 분석 및 추천 후보 생성")
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--output", default="docs/data/latest.json")
    parser.add_argument("--send-email", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(load_settings(Path(args.settings)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"분석 결과 저장: {output} ({len(report['recommendations'])}개 후보)")
    should_send = args.send_email or os.getenv("SEND_EMAIL", "").lower() in {"1", "true", "yes"}
    if should_send:
        send_email(report)


if __name__ == "__main__":
    main()
