"""Public stock-market context, kept separate from stock recommendation scores."""
from __future__ import annotations

import csv
import io
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .indicators import rsi

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_SOURCE = "https://www.cnn.com/markets/fear-and-greed"
VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
VIX_SOURCE = "https://www.cboe.com/tradable_products/vix/vix_historical_data/"
KIS_SOURCE = "https://apiportal.koreainvestment.com/"
KST = timezone(timedelta(hours=9))


def number(value: Any) -> float | None:
    try:
        result = float(value) if not isinstance(value, bool) else math.nan
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def dated(rows: list[dict], now: datetime) -> list[dict]:
    clean = {}
    for row in rows:
        try:
            date = str(row["date"])[:10]
            parsed = datetime.strptime(date, "%Y-%m-%d").date()
            value = number(row["value"])
            if parsed <= now.astimezone(KST).date() and value is not None:
                clean[date] = {"date": date, "value": value}
        except (KeyError, ValueError, TypeError):
            continue
    return [clean[key] for key in sorted(clean)]


def rating(score: float) -> str:
    return "극도의 공포" if score < 25 else "공포" if score < 45 else "중립" if score < 55 else "탐욕" if score < 75 else "극도의 탐욕"


def stale(date: str | None, now: datetime, days: int = 5) -> bool:
    return bool(date and (now.astimezone(KST).date() - datetime.strptime(date[:10], "%Y-%m-%d").date()).days > days)


def volatility(prices: list[float]) -> float:
    changes = [math.log(b / a) for a, b in zip(prices[-21:-1], prices[-20:])]
    return statistics.stdev(changes) * math.sqrt(252) * 100


def proxy_components(prices: list[float]) -> list[dict]:
    trend = (prices[-1] / statistics.mean(prices[-50:]) - 1) * 100
    momentum = (prices[-1] / prices[-21] - 1) * 100
    vols = [volatility(prices[:end]) for end in range(max(21, len(prices) - 59), len(prices) + 1)]
    current_vol = vols[-1]
    percentile = sum(value < current_vol for value in vols) + .5 * sum(value == current_vol for value in vols)
    clamp = lambda value: round(max(0, min(100, value)), 2)
    return [
        {"label": "RSI(14)", "value": round(rsi(prices), 2) if len(set(prices)) > 1 else 50,
         "unit": "", "score": clamp(rsi(prices)) if len(set(prices)) > 1 else 50},
        {"label": "50일 이동평균 이격", "value": round(trend, 2), "unit": "%", "score": clamp(50 + 5 * trend)},
        {"label": "20거래일 수익률", "value": round(momentum, 2), "unit": "%", "score": clamp(50 + 2.5 * momentum)},
        {"label": "20일 실현변동성", "value": round(current_vol, 2), "unit": "%",
         "score": clamp(100 * (1 - percentile / len(vols)))},
    ]


def proxy_sentiment(benchmark: dict, market: str, now: datetime) -> dict:
    rows = dated([{"date": row.get("date"), "value": row.get("price")} for row in benchmark.get("history", [])], now)
    rows = [row for row in rows if row["value"] > 0]
    base = {"kind": "proxy", "label": ("미국" if market == "us" else "국내") + " 공포·탐욕 · 자체 산출",
            "source": "한국투자증권 시세 · 대시보드 자체 계산", "source_url": KIS_SOURCE,
            "benchmark": benchmark.get("name", "대표 ETF"), "score": None, "history": [], "components": [],
            "note": "대표 ETF 기반 참고 심리지수이며 CNN·한국거래소 공표 지수가 아닙니다. 장중 당일 봉은 변동할 수 있으며 종목 추천점수에는 반영하지 않습니다.",
            "methodology": "최근 최소 60개 종가로 계산. RSI14, clamp(50+5×50일선 이격률), clamp(50+2.5×20거래일 수익률), "
                           "100×(1−최근 60개 관측 내 20일 변동성의 중간순위 백분위)를 동일 가중 평균. 각 성분은 0~100. "
                           "변동성은 로그수익률 표본표준편차×√252. 과거 점수는 해당 시점까지의 자료만 사용합니다."}
    if len(rows) < 60:
        return {**base, "reason": "대표 ETF의 유효한 종가 60개 이상이 필요합니다."}
    prices = [row["value"] for row in rows]
    history = []
    for end in range(60, len(rows) + 1):
        parts = proxy_components(prices[:end])
        history.append({"date": rows[end - 1]["date"], "value": round(statistics.mean(part["score"] for part in parts), 1)})
    score = history[-1]["value"]
    return {**base, "score": score, "rating": rating(score), "date": history[-1]["date"],
            "stale": stale(history[-1]["date"], now), "history": history[-60:], "components": proxy_components(prices),
            "change": round(score - history[-2]["value"], 1) if len(history) > 1 else None}


def parse_cnn(payload: dict, now: datetime) -> dict:
    current = payload.get("fear_and_greed") or {}
    score = number(current.get("score"))
    stamp = current.get("timestamp")
    if isinstance(stamp, (int, float)):
        at = datetime.fromtimestamp(stamp / (1000 if stamp > 1e11 else 1), timezone.utc)
    else:
        at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("CNN observation has no timezone")
    if score is None or not 0 <= score <= 100 or at > now + timedelta(minutes=5):
        raise ValueError("Invalid CNN observation")
    history = []
    for row in (payload.get("fear_and_greed_historical") or {}).get("data", []):
        value, timestamp = number(row.get("y")), number(row.get("x"))
        if value is None or not 0 <= value <= 100 or timestamp is None:
            continue
        date = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
        if date <= at:
            history.append({"date": date.strftime("%Y-%m-%d"), "value": value})
    previous = number(current.get("previous_close"))
    return {"kind": "published", "label": "CNN 공포·탐욕지수", "score": round(score, 1), "rating": rating(score),
            "date": at.strftime("%Y-%m-%d"), "observed_at": at.isoformat(), "stale": stale(at.isoformat(), now),
            "change": round(score - previous, 1) if previous is not None and 0 <= previous <= 100 else None,
            "source": "CNN Business", "source_url": CNN_SOURCE, "history": dated(history, now)[-90:], "components": [],
            "note": "CNN이 공표한 미국 시장 심리지수입니다. 종목 추천점수에는 반영하지 않습니다.",
            "methodology": "CNN의 모멘텀·주가강도·시장폭·풋콜·변동성·하이일드 수요·안전자산 수요 등 7개 성분을 결합한 0~100 지수."}


def parse_csv(text: str, column: str, now: datetime, vix: bool = False) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        try:
            date = datetime.strptime(row["DATE"], "%m/%d/%Y").strftime("%Y-%m-%d") if vix else row.get("observation_date", row.get("DATE"))
            rows.append({"date": date, "value": row[column]})
        except (ValueError, KeyError, TypeError):
            continue
    return dated(rows, now)


def indicator(id: str, label: str, rows: list[dict], unit: str, source: str, url: str, note: str,
              now: datetime, change_unit: str | None = None, change_scale: float = 1, max_age: int = 5) -> dict:
    latest = rows[-1] if rows else {}
    delta = (rows[-1]["value"] - rows[-2]["value"]) * change_scale if len(rows) > 1 else None
    return {"id": id, "label": label, "value": latest.get("value"), "date": latest.get("date"),
            "unit": unit, "change": round(delta, 2) if delta is not None else None, "change_unit": change_unit or unit,
            "source": source, "source_url": url, "note": note, "stale": stale(latest.get("date"), now, max_age)}


def benchmark_indicators(report: dict, now: datetime) -> list[dict]:
    benchmark = report.get("benchmark") or {}
    name = benchmark.get("name", "대표 ETF")
    history = dated([{"date": row.get("date"), "value": row.get("price")} for row in benchmark.get("history", [])], now)
    history = [row for row in history if row["value"] > 0]
    trend, drawdown, vols = [], [], []
    for end in range(21, len(history) + 1):
        prices = [row["value"] for row in history[:end]]
        date = history[end - 1]["date"]
        vols.append({"date": date, "value": volatility(prices)})
        drawdown.append({"date": date, "value": (prices[-1] / max(prices[-60:]) - 1) * 100})
        if end >= 50:
            trend.append({"date": date, "value": (prices[-1] / statistics.mean(prices[-50:]) - 1) * 100})
    date = history[-1]["date"] if history else None
    samples = [row for row in report.get("rankings", [])
               if number(row.get("price")) is not None and number(row.get("ema50")) is not None
               and row.get("history") and row["history"][-1].get("date") == date]
    above = sum(number(row["price"]) > number(row["ema50"]) for row in samples)
    breadth = [{"date": date, "value": above / len(samples) * 100}] if samples else []
    return [
        indicator("trend", "대표 ETF 50일선 이격", trend, "%", "한국투자증권", KIS_SOURCE, f"{name}: 0% 위는 50일선 상회, 아래는 하회.", now, "%p"),
        indicator("drawdown", "최근 최대 60거래일 고점 대비", drawdown, "%", "한국투자증권", KIS_SOURCE, f"{name} 종가 기준. 고점에서 얼마나 하락했는지 봅니다.", now, "%p"),
        indicator("breadth", "분석종목 50일선 상회 비율", breadth, "%", "한국투자증권", KIS_SOURCE,
                  f"분석대상 중 같은 날짜에 비교 가능한 {len(samples)}개 중 {above}개. 전체 시장 통계가 아닙니다.", now, "%p"),
        indicator("realized_vol", "대표 ETF 20일 실현변동성", vols, "%", "한국투자증권", KIS_SOURCE,
                  f"{name}: 과거 20일 로그수익률 기준 연율(252거래일). 미래 예상변동성·VKOSPI와 다릅니다.", now, "%p"),
    ]


def _download(name: str, now: datetime):
    series = {"yield": "DGS10", "fx": "DEXKOUS"}
    url = CNN_URL if name == "cnn" else VIX_URL if name == "vix" else (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series[name]}&cosd={(now - timedelta(days=90)):%Y-%m-%d}")
    response = requests.get(url, headers={"User-Agent": "coin-recomand/1.0", "Accept": "application/json,text/csv"}, timeout=10)
    response.raise_for_status()
    return parse_cnn(response.json(), now) if name == "cnn" else parse_csv(response.text, "CLOSE" if name == "vix" else series[name], now, name == "vix")


def add_market_context(reports: dict[str, dict], now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    collected, errors = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(_download, name, now) for name in ("cnn", "vix", "yield", "fx")}
        for name, future in futures.items():
            try:
                collected[name] = future.result()
            except Exception as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                errors[name] = f"HTTP {status}" if status else "자료 확인 불가"
    for market in ("us", "kr"):
        report = reports[market]
        sentiment = proxy_sentiment(report.get("benchmark") or {}, market, now)
        if market == "us":
            sentiment = collected.get("cnn") or {**sentiment, "notice": f"CNN 공표값 미수집({errors.get('cnn', '자료 없음')}). 자체 산출값을 표시합니다.", "published_source_url": CNN_SOURCE}
        cards = benchmark_indicators(report, now)
        if market == "us":
            cards = [indicator("vix", "VIX · 미국 예상변동성", collected.get("vix", []), "pt", "Cboe", VIX_SOURCE,
                               "S&P 500 옵션의 향후 30일 예상변동성. 높아질수록 가격 변동 불확실성이 큽니다.", now),
                     indicator("us10y", "미 국채 10년 금리", collected.get("yield", []), "%", "연준 · FRED", "https://fred.stlouisfed.org/series/DGS10",
                               "금리 상승은 성장주 할인율 부담과 연결될 수 있습니다. 일별 고시, 발표 시차 있음.", now, "bp", 100)] + cards[:3]
        else:
            cards = [indicator("usdkrw", "원·달러 환율", collected.get("fx", []), "원/USD", "연준 · FRED", "https://fred.stlouisfed.org/series/DEXKOUS",
                               "달러당 원화. 뉴욕 정오 고시의 일별 자료이며 주간 공표 시차가 있습니다. 실시간 환율이 아닙니다.", now, "원", max_age=10)] + cards
        report["market_context"] = {"generated_at": now.isoformat(), "sentiment": sentiment, "indicators": cards,
                                    "note": "일별 관측값 기준이며 시차가 있습니다. 휴장일에는 최근 관측일을 표시합니다. 미수집 값을 0이나 중립으로 대체하지 않습니다."}
