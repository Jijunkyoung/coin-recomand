"""Forward-only paper signal research. Never places orders or rewrites predictions."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

VERSION = "research-v1"
HORIZONS = (1, 3, 7)
COSTS = {"fee_bps_per_side": 5, "slippage_bps_per_side": 10}
MAX_DELAY = timedelta(hours=6)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Research timestamps require timezone")
    return result.astimezone(timezone.utc)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def net_return(entry, exit_price, costs):
    fee = costs["fee_bps_per_side"] / 10000
    slip = costs["slippage_bps_per_side"] / 10000
    return (exit_price * (1 - slip) * (1 - fee) / (entry * (1 + slip) * (1 + fee)) - 1) * 100


def features(coin, report, prior):
    mentions = coin.get("community_mentions") or {}
    sources = sorted(k for k, v in mentions.items() if number(v))
    exposure = coin.get("community_exposure_rate")
    previous = (prior or {}).get(coin["market"], {})
    base = previous.get("exposure")
    comparable = sources and sources == previous.get("sources") and number(exposure) and number(base) and base > 0
    growth = exposure / base if comparable else None
    ret = coin.get("return_7d")
    btc = report["market"]["bitcoin"].get("return_7d")
    relative = ret - btc if number(ret) and number(btc) else None
    # Presence only: an official announcement is not automatically bullish.
    official = sorted({e.get("source_url") for e in report.get("major_events", [])
                       if e.get("official_source") and e.get("source_url")
                       and coin.get("symbol") in (e.get("related_symbols") or [])})
    tokens = coin.get("tokenomics") or {}
    safe = (number(coin.get("rsi")) and coin["rsi"] < 70
            and number(ret) and -5 <= ret <= 20
            and number(coin.get("trade_value_24h")) and coin["trade_value_24h"] >= 1_000_000_000
            and report["market"].get("regime") != "하락")
    # Missing unlock data does not imply absence of selling pressure.
    unlock_clear = tokens.get("unlock_data_available") is True and not tokens.get("next_unlock")
    return {"relative_7d": relative, "attention_growth": growth,
            "active_sources": sum(number(v) and v > 0 for v in mentions.values()),
            "official_urls": official, "risk_pass": bool(safe and unlock_clear),
            "exposure": exposure, "sources": sources,
            "unlock_verified_clear": unlock_clear}


def vector(f):
    if not number(f.get("relative_7d")) or not number(f.get("attention_growth")):
        return None
    return [1, max(-3, min(3, f["relative_7d"] / 10)),
            max(-3, min(3, math.log(max(.01, f["attention_growth"])))),
            min(4, f.get("active_sources", 0)) / 4, int(bool(f.get("official_urls")))]


def probability(weights, x):
    return 1 / (1 + math.exp(-max(-30, min(30, sum(a * b for a, b in zip(weights, x))))))


def train(records, now):
    # Seven-day embargo; only outcomes actually observed before cutoff are usable.
    cutoff = now - timedelta(days=7)
    eligible = [r for r in records if r["version"] == VERSION and vector(r["features"]) is not None
                and r["outcomes"].get("3", {}).get("status") == "complete"
                and timestamp(r["outcomes"]["3"]["exit_at"]) < cutoff]
    days = len({r["day"] for r in eligible})
    model = {"status": "자료 부족", "samples": len(eligible), "days": days,
             "cutoff": cutoff.isoformat(), "weights": None}
    labels = [int(r["outcomes"]["3"]["net_pct"] > 0) for r in eligible]
    if days < 60 or len(eligible) < 200 or len(set(labels)) < 2:
        return model
    xs = [vector(r["features"]) for r in eligible]
    weights = [0.] * 5
    for _ in range(150):
        errors = [probability(weights, x) - y for x, y in zip(xs, labels)]
        weights = [w - .1 * (mean(e * x[j] for e, x in zip(errors, xs)) + (.02 * w if j else 0))
                   for j, w in enumerate(weights)]
    model.update(status="실험 학습 완료·수익성 미검증", weights=weights,
                 trained_at=now.isoformat(),
                 id=hashlib.sha256(json.dumps([cutoff.isoformat(), weights]).encode()).hexdigest()[:12])
    return model


def settle(record, prices, now):
    at = timestamp(record["observed_at"])
    price, btc = prices.get(record["market"]), prices.get("KRW-BTC")
    valid = all(number(p) and p > 0 for p in (price, btc))
    if record["status"] == "pending_entry":
        if now > at + MAX_DELAY:
            record["status"] = "entry_missing"
        elif now > at and valid:
            record.update(status="tracking", entry_at=now.isoformat(), entry_price=price,
                          btc_entry=btc, peak=price, sampled_drawdown_pct=0.)
        return
    if record["status"] != "tracking":
        return
    if valid:
        record["peak"] = max(record["peak"], price)
        record["sampled_drawdown_pct"] = min(record["sampled_drawdown_pct"], (price / record["peak"] - 1) * 100)
    for days in HORIZONS:
        key = str(days)
        due = timestamp(record["entry_at"]) + timedelta(days=days)
        if key in record["outcomes"] or now < due:
            continue
        if now > due + MAX_DELAY:
            record["outcomes"][key] = {"status": "price_missing"}
        elif valid:
            record["outcomes"][key] = {
                "status": "complete", "exit_at": now.isoformat(), "exit_price": price,
                "net_pct": net_return(record["entry_price"], price, record["costs"]),
                "btc_net_pct": net_return(record["btc_entry"], btc, record["costs"]),
                "sampled_drawdown_pct": record["sampled_drawdown_pct"],
                "double_cost_net_pct": net_return(record["entry_price"], price,
                                                  {k: v * 2 for k, v in record["costs"].items()})}
    if len(record["outcomes"]) == len(HORIZONS):
        record["status"] = "closed"


def update(state, report, prices):
    now = timestamp(report["generated_at"])
    if state.get("schema_version", 1) != 1:
        raise ValueError("Unsupported research state schema")
    if state.get("last_at") and now <= timestamp(state["last_at"]):
        return state  # Retries and stale snapshots must not rewrite history.
    state.setdefault("schema_version", 1)
    records = state.setdefault("records", [])
    state.setdefault("daily", [])
    for record in records:
        settle(record, prices, now)
    day = now.astimezone(timezone(timedelta(hours=9))).date().isoformat()
    if not any(d["day"] == day for d in state["daily"]):
        prior = next((d["coins"] for d in reversed(state["daily"])
                      if timedelta(hours=20) <= now - timestamp(d["at"]) <= timedelta(hours=48)), None)
        model = train(records, now)
        state["model"] = model
        coins = {}
        for coin in report.get("alt_rankings", []):
            f = features(coin, report, prior)
            coins[coin["market"]] = {"exposure": f["exposure"], "sources": f["sources"]}
            x = vector(f)
            p = probability(model["weights"], x) if model["weights"] is not None and x else None
            selected = ["universe"]
            if "매수" in str(coin.get("decision", "")):
                selected.append("existing")
            if number(coin.get("price")) and number(coin.get("ema20")) and number(coin.get("ema50")) and coin["price"] > coin["ema20"] > coin["ema50"]:
                selected.append("trend")
            if f["risk_pass"] and f["attention_growth"] is not None and f["attention_growth"] >= 2 and f["active_sources"] >= 2 and f["relative_7d"] is not None and f["relative_7d"] > 0 and f["official_urls"]:
                selected.append("attention_news")
            if f["risk_pass"] and p is not None and p >= .6:
                selected.append("learned")
            records.append({"id": f"{VERSION}:{day}:{coin['market']}", "version": VERSION,
                            "day": day, "observed_at": now.isoformat(), "market": coin["market"],
                            "score": coin.get("score"), "decision": coin.get("decision"),
                            "features": f, "strategies": selected, "prediction": p,
                            "model_id": model.get("id"), "costs": dict(COSTS),
                            "status": "pending_entry", "outcomes": {}})
        state["daily"].append({"day": day, "at": now.isoformat(), "coins": coins})
    state["last_at"] = now.isoformat()
    return state


def summary(state):
    records = state.get("records", [])
    rows = []
    for strategy in ("existing", "trend", "attention_news", "learned", "universe"):
        selected = [r for r in records if strategy in r["strategies"]]
        for days in HORIZONS:
            done = [r["outcomes"][str(days)] for r in selected if r["outcomes"].get(str(days), {}).get("status") == "complete"]
            rows.append({"strategy": strategy, "days": days, "signals": len(selected), "completed": len(done),
                         "missing": sum(r["status"] == "entry_missing" or r["outcomes"].get(str(days), {}).get("status") == "price_missing" for r in selected),
                         "mean_net_pct": mean(d["net_pct"] for d in done) if done else None,
                         "win_rate": mean(d["net_pct"] > 0 for d in done) * 100 if done else None,
                         "excess_btc_pct": mean(d["net_pct"] - d["btc_net_pct"] for d in done) if done else None,
                         "double_cost_pct": mean(d["double_cost_net_pct"] for d in done) if done else None,
                         "worst_sampled_drawdown_pct": min((d["sampled_drawdown_pct"] for d in done), default=None)})
    return {"version": VERSION, "updated_at": state.get("last_at"), "costs": COSTS,
            "status": "모의 연구·수익성 미검증", "observed_days": len(state.get("daily", [])),
            "model": state.get("model"), "comparisons": rows,
            "recent": list(reversed(records[-100:])),
            "limitations": ["표의 값은 신호별 평균이며 복리·계좌 수익률이 아닙니다. 중복 보유와 자금 한도는 아직 모델링하지 않습니다.",
                            "BTC는 동일 진입·청산 기간 비교이며 장기 매수보유 지수가 아닙니다. 현금 수익률 기준은 0%입니다.",
                            "최대 하락은 수집 시점 가격 기준입니다. 수집 사이 급락·체결 실패·거래소 장애를 반영하지 못합니다.",
                            "시장당 한국시간 하루 첫 분석을 고정합니다. 다음 수집 가격으로 진입하며 6시간 넘게 지연되면 미평가 처리합니다.",
                            "언락 미수집은 안전으로 간주하지 않습니다. 공식 뉴스 존재는 호재 판정이 아니며, 기사 의미·원문 중복 판별은 후속 과제입니다.",
                            "학습은 7일 간격을 둔 과거 확정 결과만 사용합니다. 최소 60개 관측일·200개 표본 필요. 확률 보정 및 독립 최종시험 전 실험값입니다.",
                            "학습 모델은 모의 신호만 생성하며 기존 추천·메일·실제 주문을 변경하지 않습니다."]}


def main():
    report = json.loads(Path("docs/data/latest.json").read_text())
    age = datetime.now(timezone.utc) - timestamp(report["generated_at"])
    if age < timedelta(0) or age > timedelta(hours=2):
        raise ValueError("Research requires a fresh analysis (no historical report replay)")
    path = Path("research-state/state.json")
    state = json.loads(path.read_text()) if path.exists() else {}
    # Live quotes include delisted-from-screen coins; unavailable quotes stay missing.
    import requests
    markets = {r["market"] for r in state.get("records", []) if r["status"] in {"pending_entry", "tracking"}}
    markets.update(c["market"] for c in report.get("alt_rankings", []))
    markets.add("KRW-BTC")
    # Resolve currently tradable markets, so a removed symbol cannot break the entire batch.
    response = requests.get("https://api.upbit.com/v1/market/all", timeout=30)
    response.raise_for_status()
    available = {r["market"] for r in response.json()}
    markets = sorted(markets & available)
    prices = {}
    for start in range(0, len(markets), 50):
        response = requests.get("https://api.upbit.com/v1/ticker", params={"markets": ",".join(markets[start:start + 50])}, timeout=30)
        response.raise_for_status()
        prices.update({r["market"]: r["trade_price"] for r in response.json()})
    # Observation time reflects when quotes became available, never the start of a long analysis.
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    state = update(state, report, prices)
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, allow_nan=False))
    temporary.replace(path)
    Path("docs/data/research.json").write_text(json.dumps(summary(state), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
