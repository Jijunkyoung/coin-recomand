from __future__ import annotations

import argparse
import json
import os
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
    try:
        reddit = client.reddit_mentions(aliases)
    except Exception as exc:
        reddit = {}
        warnings.append(f"Reddit 언급 수 미수집: {type(exc).__name__}")

    analyzed: list[dict[str, Any]] = []
    for ticker in candidates:
        market = ticker["market"]
        symbol = market.split("-", 1)[1]
        try:
            metrics = technical_metrics(client.upbit_daily_candles(market, settings["upbit_candle_days"]))
            metrics.update(
                {
                    "trending_rank": trending.get(symbol),
                    "reddit_mentions": reddit.get(symbol),
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
                    "reasons": reasons[:4],
                    "risks": risks[:3],
                    **metrics,
                }
            )
        except Exception as exc:
            warnings.append(f"{market} 분석 제외: {type(exc).__name__}")
        time.sleep(0.12)
    analyzed.sort(key=lambda coin: (coin["score"], coin["trade_value_24h"]), reverse=True)
    top = analyzed[: settings["recommendation_count"]]
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
            "alt": "기술지표 70% 내외 + 거래량·커뮤니티 관심도 + 변동성 위험 감점",
            "execution": "실제 주문 없음, 하락장 신규 매수 차단, 후보는 분할 접근 전제",
        },
        "data_quality": {"status": "주의" if warnings else "정상", "warnings": warnings},
        "sources": [
            {"name": "Upbit", "url": "https://global-docs.upbit.com/reference/list-tickers"},
            {"name": "Coin Metrics", "url": "https://docs.coinmetrics.io/api/v4"},
            {"name": "CoinGecko", "url": "https://docs.coingecko.com/docs/keyless-public-api"},
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
