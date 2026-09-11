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


class InsufficientHistoryError(ValueError):
    def __init__(self, available: int, required: int = 60) -> None:
        self.available = available
        self.required = required
        super().__init__(f"거래이력 부족 ({available}일/최소 {required}일)")


def warning_reason(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status == 403:
        return "HTTP 403 접근 거부(수집 실행환경 제한)"
    if status:
        return f"HTTP {status}"
    message = str(exc).strip()
    return message if message else type(exc).__name__


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


def summarize_unlock(
    metadata: dict[str, Any] | None,
    circulating_supply: float | None,
    now: datetime | None = None,
    total_supply: float | None = None,
) -> dict[str, Any] | None:
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
                elif isinstance(item, (int, float, str)):
                    events.append({"date": key, "amount": item})
    current = now or datetime.now(timezone.utc)
    upcoming: list[tuple[datetime, dict[str, Any]]] = []
    for event in events:
        date = _parse_datetime(next((event.get(key) for key in ("date", "unlock_date", "unlockDate", "release_date", "releaseDate", "timestamp", "time") if event.get(key) is not None), None))
        if date and date >= current:
            upcoming.append((date, event))
    if not upcoming:
        return None
    date, event = min(upcoming, key=lambda item: item[0])
    amount_value = next(
        (
            event.get(key)
            for key in ("amount", "token_amount", "tokenAmount", "tokens", "tokens_to_unlock", "tokensToUnlock", "unlock_amount", "unlockAmount", "quantity", "value")
            if event.get(key) is not None
        ),
        None,
    )
    try:
        amount = float(amount_value) if amount_value is not None else None
    except (TypeError, ValueError):
        amount = None
    percent = amount / circulating_supply * 100 if amount is not None and circulating_supply else None
    if percent is None:
        percent_value = next(
            (
                event.get(key)
                for key in ("percent_circulating", "percentage", "percent", "unlock_percentage", "unlockPercentage", "percentage_of_circulating_supply")
                if event.get(key) is not None
            ),
            None,
        )
        try:
            percent = float(percent_value) if percent_value is not None else None
            if percent is not None and 0 < percent <= 1:
                percent *= 100
        except (TypeError, ValueError):
            percent = None
    total_percent_value = next(
        (
            event.get(key)
            for key in ("percentage_of_total_supply", "percent_total_supply", "percentTotalSupply", "total_supply_percentage")
            if event.get(key) is not None
        ),
        None,
    )
    try:
        total_percent = float(total_percent_value) if total_percent_value is not None else None
        if total_percent is not None and 0 < total_percent <= 1:
            total_percent *= 100
    except (TypeError, ValueError):
        total_percent = None
    if amount is None and total_percent is not None and total_supply:
        amount = total_supply * total_percent / 100
    if percent is None and amount is not None and circulating_supply:
        percent = amount / circulating_supply * 100
    return {
        "date": date.date().isoformat(),
        "days_until": max(0, (date - current).days),
        "amount": round(amount, 4) if amount is not None else None,
        "percent_circulating": round(percent, 2) if percent is not None else None,
        "amount_available": amount is not None,
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
            "next_unlock": summarize_unlock(
                unlock_metadata,
                float(circulating) if circulating else None,
                now,
                float(total) if total else None,
            ),
            "unlock_data_available": unlock_metadata is not None,
            "project_notice": notice or None,
        },
        "coingecko_id": details.get("id"),
    }


def technical_metrics(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < 60:
        raise InsufficientHistoryError(len(candles))
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
    notices: list[str] = []
    market_rows = client.upbit_markets()
    market_names = {row["market"]: row.get("korean_name") or row["market"] for row in market_rows}
    english_names = {row["market"]: row.get("english_name") or row["market"] for row in market_rows}
    tickers = client.upbit_tickers(list(market_names))
    tickers.sort(key=lambda row: float(row.get("acc_trade_price_24h") or 0), reverse=True)

    btc_candles = client.upbit_daily_candles("KRW-BTC", settings["upbit_candle_days"])
    bitcoin = technical_metrics(btc_candles)
    bitcoin["market"] = "KRW-BTC"
    try:
        mvrv_result = client.bitcoin_mvrv_z()
        if isinstance(mvrv_result, tuple):
            mvrv_value, mvrv_source = mvrv_result
        else:
            mvrv_value, mvrv_source = mvrv_result, None
        bitcoin["mvrv_z"] = round_or_none(mvrv_value)
        bitcoin["mvrv_source"] = mvrv_source
    except Exception as exc:
        bitcoin["mvrv_z"] = None
        bitcoin["mvrv_source"] = None
        warnings.append(f"MVRV Z-Score 미수집: {warning_reason(exc)}")
    try:
        fear_greed = client.fear_and_greed()
        bitcoin["fear_greed"] = fear_greed["value"]
    except Exception as exc:
        fear_greed = {"value": None, "classification": "미수집", "previous": None}
        bitcoin["fear_greed"] = None
        warnings.append(f"공포·탐욕 지수 미수집: {type(exc).__name__}")
    market_score, regime, market_reasons = market_regime(bitcoin)

    try:
        liquidity = client.defillama_market_liquidity()
    except Exception as exc:
        liquidity = None
        warnings.append(f"DefiLlama 유동성지표 미수집: {warning_reason(exc)}")

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
            warnings.append(f"{source_names[source]} 언급 수 미수집: {warning_reason(exc)}")

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
                    "analysis_scope": "기술·커뮤니티 분석",
                    **metrics,
                }
            )
        except InsufficientHistoryError as exc:
            notices.append(f"{market} 분석 제외: {exc}")
        except Exception as exc:
            warnings.append(f"{market} 분석 제외: {warning_reason(exc)}")
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
            coin.update({"score": score, "decision": recommendation_label(score, regime), "reasons": reasons[:6], "risks": risks[:5], "analysis_scope": "정밀분석"})
        except Exception as exc:
            warnings.append(f"{coin['symbol']} 프로젝트 정보 미수집: {type(exc).__name__}")
        time.sleep(0.8)
    analyzed.sort(key=lambda coin: (coin["score"], coin["trade_value_24h"]), reverse=True)
    for rank, coin in enumerate(analyzed, start=1):
        coin["rank"] = rank
    enriched.sort(key=lambda coin: (coin["score"], coin["trade_value_24h"]), reverse=True)
    top = enriched[: settings["recommendation_count"]]
    try:
        news_issues = client.crypto_news(["BTC", "ETH", *(coin["symbol"] for coin in top)], limit=7)
    except Exception as exc:
        news_issues = []
        warnings.append(f"주요 코인 이슈 미수집: {warning_reason(exc)}")
    try:
        upcoming_events = client.coinmarketcal_events(["BTC", "ETH", *(coin["symbol"] for coin in top)], limit=8)
        if upcoming_events is None:
            warnings.append("CoinMarketCal 일정 미수집: COINMARKETCAL_API_KEY Secret 미인식")
            upcoming_events = []
    except Exception as exc:
        upcoming_events = []
        warnings.append(f"CoinMarketCal 일정 미수집: {warning_reason(exc)}")
    ranking_fields = (
        "rank", "market", "symbol", "name", "english_name", "score", "decision", "analysis_scope", "reasons", "risks",
        "price", "ema20", "ema50", "rsi", "macd_histogram", "return_7d", "return_30d", "volume_ratio",
        "volatility", "trending_rank", "community_mentions", "community_total", "community_sources",
        "community_exposure_rate", "trade_value_24h", "development", "tokenomics", "coingecko_id", "sparkline", "history",
    )
    alt_rankings = [{field: coin.get(field) for field in ranking_fields} for coin in analyzed]
    now = datetime.now(timezone.utc)
    return {
        "schema_version": 3,
        "generated_at": now.isoformat(),
        "generated_at_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
        "market": {
            "score": market_score,
            "regime": regime,
            "reasons": market_reasons,
            "bitcoin": bitcoin,
            "fear_greed": fear_greed,
            "liquidity": liquidity,
        },
        "recommendations": top,
        "news_issues": news_issues,
        "upcoming_events": upcoming_events,
        "alt_rankings": alt_rankings,
        "screened": len(analyzed),
        "methodology": {
            "intro": "알트코인은 내부 원점수 35점에서 시작해 아래 신호를 가감하며, 이론상 최고 77점을 최종 100점으로 환산합니다. 같은 가격 흐름에서 파생된 기술 신호는 합산 상한을 두어 중복 가산을 줄입니다.",
            "groups": [
                {
                    "title": "기술 분석",
                    "range": "원점수 -18 ~ +22",
                    "items": [
                        "추세(가격·EMA20·EMA50): 정배열 +8 / 역배열 -10",
                        "RSI(14): 45~65 +4 / 75 이상 -7 / 35 미만 -3",
                        "MACD 히스토그램: 양수 +4 / 0 이하 -3",
                        "수익률: 7일 0~15%이면서 30일 3~35% +6 / 7일 25% 초과 또는 30일 60% 초과 -8",
                        "위 항목 합계는 최대 +22, 최소 -18로 제한",
                    ],
                },
                {
                    "title": "거래량·관심도",
                    "range": "원점수 -4 ~ +9",
                    "items": [
                        "최근 7일 거래대금 ÷ 30일 평균: 1.1~3배 +5 / 0.65배 미만 -4",
                        "CoinGecko 24시간 인기 검색: 1~3위 +4 / 4~6위 +3 / 7~9위 +2 / 그 밖의 순위 +1",
                    ],
                },
                {
                    "title": "커뮤니티 노출",
                    "range": "원점수 0 ~ +5",
                    "items": [
                        "한국시간 당일 Reddit·디시인사이드·코인판 게시물만 집계하며 한 게시물은 코인별 1회로 계산",
                        "1회 이상 +1 / 3회 이상 추가 +1 / 7회 이상 추가 +1",
                        "언급된 커뮤니티가 늘 때마다 +1(추가 최대 2점), 전체 표본 대비 노출률 3% 이상 +1",
                        "합계는 최대 +5점이며 미수집 출처는 0회로 간주하지 않고 표본·배점에서 제외",
                    ],
                },
                {
                    "title": "개발·토크노믹스",
                    "range": "원점수 상한 +6 / 위험별 감점",
                    "items": [
                        "공식 GitHub 최근 30일 커밋: 20건 이상 +3 / 5건 이상 +2, 45일 이내 릴리스 +2(개발 호재 합계 최대 +4)",
                        "30일 커밋 0건이고 마지막 커밋 120일 이상 경과: -5",
                        "유통 비율: 35% 미만 -6 / 35~55% 미만 -4 / 85% 이상 +2",
                        "언락: 30일 이내 유통량 5% 이상 -14, 1% 이상 -9, 수량 미확인 -6~-8, 소규모 -1~-4 / 31~60일 대규모 -10·그 외 -4",
                        "30일 연환산 변동성 120% 초과: -8",
                    ],
                },
                {
                    "title": "비트코인 시장 국면",
                    "range": "원점수 0 ~ -20",
                    "items": [
                        "BTC 상승 국면: 추가 조정 없음 / 중립: -4 / 하락: -20",
                        "하락 국면에서는 점수가 높아도 신규 매수 후보로 표시하지 않음",
                    ],
                },
            ],
            "decisions": [
                "상승 국면: 87점 이상 분할매수 후보 / 68~86점 관찰 / 67점 이하 보류",
                "중립 국면: 94점 이상 분할매수 후보 / 68~93점 관찰 / 67점 이하 보류",
                "하락 국면: 71점 이상 관찰 / 70점 이하 보류",
            ],
            "execution": "실제 주문은 실행하지 않으며, 분할매수 후보도 손절·비중·호재 출처를 다시 확인하는 연구용 신호입니다.",
        },
        "data_quality": {"status": "주의" if warnings else "정상", "warnings": warnings, "notices": notices},
        "sources": [
            {"name": "Upbit", "url": "https://global-docs.upbit.com/reference/list-tickers"},
            {"name": "Blockchain.com", "url": "https://www.blockchain.com/explorer/api/charts_api"},
            {"name": "CoinGecko", "url": "https://docs.coingecko.com/docs/keyless-public-api"},
            {"name": "GitHub", "url": "https://docs.github.com/rest/commits/commits"},
            {"name": "Mobula", "url": "https://docs.mobula.io/guides/token-unlock"},
            {"name": "Reddit", "url": "https://www.reddit.com/r/CryptoCurrency/"},
            {"name": "DCInside", "url": "https://gall.dcinside.com/board/lists/?id=bitcoins_new1"},
            {"name": "Coinpan", "url": "https://coinpan.com/free"},
            {"name": "Alternative.me", "url": "https://alternative.me/crypto/fear-and-greed-index/"},
            {"name": "Google News RSS", "url": "https://news.google.com/"},
            {"name": "CoinMarketCal", "url": "https://coinmarketcal.com/developer"},
            {"name": "DefiLlama", "url": "https://api-docs.defillama.com/"},
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
