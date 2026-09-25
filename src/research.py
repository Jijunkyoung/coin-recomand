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
SURGE_VERSION = "surge-track-v1"
SURGE_HORIZONS = (1, 4, 12, 24)
SURGE_WINDOW_HOURS = 6
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


def _event_snapshot(report, symbol):
    events = []
    seen = set()
    for event in report.get("major_events", []):
        if symbol not in (event.get("related_symbols") or []):
            continue
        key = str(event.get("id") or event.get("source_url") or event.get("url") or event.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        events.append({"key": key, "title": str(event.get("title") or "")[:220],
                       "importance": event.get("importance") or event.get("impact") or "보통"})
    return events


def _current_coin(report, market):
    return next((coin for coin in report.get("alt_rankings", []) if coin.get("market") == market), {})


def _development_snapshot(coin):
    development = coin.get("development") or {}
    return {"status": development.get("status"), "commits_30d": development.get("commits_30d"),
            "latest_release_name": development.get("latest_release_name"),
            "latest_release_days": development.get("latest_release_days")}


def _development_changed(initial, current):
    """Ignore the normal day-count drift unless a release or activity signal changed."""
    initial = initial or {}
    return any(initial.get(key) != current.get(key)
               for key in ("status", "commits_30d", "latest_release_name"))


def _surge_window(now):
    kst = now.astimezone(timezone(timedelta(hours=9)))
    return f"{kst.date().isoformat()}-{kst.hour // SURGE_WINDOW_HOURS}"


def _collect_surge_evidence(record, report):
    initial = {event["key"] for event in record.get("initial_events", [])}
    collected = {event["key"] for event in record.get("new_events", [])}
    for event in _event_snapshot(report, record["symbol"]):
        if event["key"] not in initial and event["key"] not in collected:
            record.setdefault("new_events", []).append(event)
            collected.add(event["key"])


def _surge_drivers(record, report):
    outcome = record.get("outcomes", {}).get("24", {})
    drivers = []
    evidence = []
    if record.get("new_events"):
        drivers.append("예측 후 관련 뉴스·이벤트")
        evidence.extend(event["title"] for event in record["new_events"][:2] if event.get("title"))
    coin = _current_coin(report, record["market"])
    current_development = _development_snapshot(coin)
    if _development_changed(record.get("initial_development"), current_development) \
            and any(current_development.values()):
        drivers.append("개발활동·릴리스 변화")
        evidence.append("개발활동 지표가 추천 시점과 달라졌습니다.")
    initial_volume = record.get("initial_volume_ratio")
    current_volume = coin.get("volume_ratio")
    peak = record.get("peak_gross_pct")
    btc_return = outcome.get("btc_gross_pct")
    if number(peak) and peak >= 10 and ((number(initial_volume) and initial_volume >= 1.5)
                                       or (number(current_volume) and current_volume >= 1.5)):
        drivers.append("코인 고유 거래대금 확대")
        evidence.append(f"관측 최고상승률 {peak:.2f}%와 거래대금 확대가 함께 나타났습니다.")
    if number(btc_return) and btc_return >= 3:
        drivers.append("비트코인·시장 동반 상승")
        evidence.append(f"같은 기간 BTC가 {btc_return:.2f}% 상승했습니다.")
    if number(record.get("initial_relative_7d_pct")) and record["initial_relative_7d_pct"] >= 10:
        drivers.append("추천 전 상대강도 지속")
    if not drivers:
        drivers.append("확인 가능한 단일 변화 요인 없음")
        evidence.append("공개 데이터만으로 가격 변화의 단일 원인을 확인하지 못했습니다.")
    return {"labels": list(dict.fromkeys(drivers)), "evidence": evidence[:4],
            "confidence": "보통" if len(drivers) >= 2 or record.get("new_events") else "낮음",
            "note": "가격과 함께 관찰된 정황이며 인과관계를 확정한 결과가 아닙니다."}


def settle_surge(record, prices, report, now):
    observed = timestamp(record["observed_at"])
    price, btc = prices.get(record["market"]), prices.get("KRW-BTC")
    valid = all(number(value) and value > 0 for value in (price, btc))
    if record["status"] == "pending_entry":
        if now > observed + MAX_DELAY:
            record["status"] = "entry_missing"
        elif now > observed and valid:
            record.update(status="tracking", entry_at=now.isoformat(), entry_price=price, btc_entry=btc,
                          peak_price=price, trough_price=price, peak_gross_pct=0., drawdown_gross_pct=0.)
        return
    if record["status"] != "tracking":
        return
    _collect_surge_evidence(record, report)
    if valid:
        record["peak_price"] = max(record["peak_price"], price)
        record["trough_price"] = min(record["trough_price"], price)
        record["peak_gross_pct"] = (record["peak_price"] / record["entry_price"] - 1) * 100
        record["drawdown_gross_pct"] = (record["trough_price"] / record["entry_price"] - 1) * 100
    for hours in SURGE_HORIZONS:
        key = str(hours)
        due = timestamp(record["entry_at"]) + timedelta(hours=hours)
        if key in record["outcomes"] or now < due:
            continue
        if now > due + MAX_DELAY:
            record["outcomes"][key] = {"status": "price_missing"}
        elif valid:
            record["outcomes"][key] = {
                "status": "complete", "exit_at": now.isoformat(), "exit_price": price,
                "gross_pct": (price / record["entry_price"] - 1) * 100,
                "net_pct": net_return(record["entry_price"], price, record["costs"]),
                "btc_gross_pct": (btc / record["btc_entry"] - 1) * 100,
                "btc_net_pct": net_return(record["btc_entry"], btc, record["costs"]),
            }
    if len(record["outcomes"]) == len(SURGE_HORIZONS):
        record["status"] = "closed"
        record["closed_at"] = now.isoformat()
        record["observed_drivers"] = _surge_drivers(record, report)


def update_surge_tracking(state, report, prices, now):
    records = state.setdefault("surge_records", [])
    for record in records:
        settle_surge(record, prices, report, now)
    window = _surge_window(now)
    if state.get("surge_last_window") == window:
        return
    candidates = (report.get("surge_research") or {}).get("candidates", [])[:10]
    if not candidates:
        return
    for candidate in candidates:
        market = candidate.get("market")
        symbol = candidate.get("symbol")
        if not market or not symbol:
            continue
        coin = _current_coin(report, market)
        records.append({
            "id": f"{SURGE_VERSION}:{window}:{market}", "version": SURGE_VERSION, "window": window,
            "observed_at": now.isoformat(), "market": market, "symbol": symbol, "name": candidate.get("name"),
            "model_probability_pct": candidate.get("model_probability_pct"),
            "feedback_adjusted_score": candidate.get("feedback_adjusted_score", candidate.get("signal_score")),
            "reasons": list(candidate.get("reasons") or []), "watch_status": candidate.get("watch_status"),
            "initial_volume_ratio": candidate.get("volume_ratio_20d"),
            "initial_relative_7d_pct": candidate.get("relative_7d_pct"),
            "initial_development_signal": candidate.get("development_signal"),
            "initial_development": _development_snapshot(coin),
            "initial_events": _event_snapshot(report, symbol), "new_events": [],
            "costs": dict(COSTS), "status": "pending_entry", "outcomes": {},
        })
    state["surge_last_window"] = window


def surge_feedback(state, now=None):
    current = now or datetime.now(timezone.utc)
    eligible = [record for record in state.get("surge_records", [])
                if record.get("status") == "closed"
                and record.get("outcomes", {}).get("24", {}).get("status") == "complete"
                and timestamp(record.get("closed_at") or record["outcomes"]["24"]["exit_at"]) <= current]
    hits = [record for record in eligible if number(record.get("peak_gross_pct")) and record["peak_gross_pct"] >= 10]
    base_rate = len(hits) / len(eligible) if eligible else None
    reason_rows = {}
    for record in eligible:
        hit = record in hits
        for reason in set(record.get("reasons") or []):
            stats = reason_rows.setdefault(reason, {"samples": 0, "hits": 0})
            stats["samples"] += 1
            stats["hits"] += int(hit)
    adjustments = {}
    if base_rate is not None and len(eligible) >= 20:
        for reason, stats in reason_rows.items():
            if stats["samples"] < 5:
                continue
            smoothed = (stats["hits"] + base_rate * 10) / (stats["samples"] + 10)
            adjustments[reason] = round(max(-5, min(5, (smoothed - base_rate) * 25)), 2)
    drivers = {}
    for record in eligible:
        for label in (record.get("observed_drivers") or {}).get("labels", []):
            drivers[label] = drivers.get(label, 0) + 1
    return {"status": "실제 추적 반영" if len(eligible) >= 20 else "자료 축적 중",
            "completed": len(eligible), "hits": len(hits),
            "hit_rate_pct": round(base_rate * 100, 2) if base_rate is not None else None,
            "reason_adjustments": adjustments, "driver_counts": drivers,
            "minimum_for_adjustment": 20}


def surge_tracking_summary(state):
    records = state.get("surge_records", [])
    feedback = surge_feedback(state)
    complete = [record for record in records if record.get("outcomes", {}).get("24", {}).get("status") == "complete"]
    peaks = [record["peak_gross_pct"] for record in complete if number(record.get("peak_gross_pct"))]
    return {"version": SURGE_VERSION, "signals": len(records), "completed_24h": len(complete),
            "hit_rate_pct": feedback["hit_rate_pct"],
            "mean_peak_pct": mean(peaks) if peaks else None,
            "mean_24h_pct": mean(record["outcomes"]["24"]["gross_pct"] for record in complete) if complete else None,
            "feedback": feedback, "recent": list(reversed(records[-100:])),
            "cause_note": "표시된 변화 요인은 공개 데이터에서 함께 관찰된 정황이며 가격 원인을 확정하지 않습니다."}


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
    update_surge_tracking(state, report, prices, now)
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
            "surge_tracking": surge_tracking_summary(state),
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
    markets.update(r["market"] for r in state.get("surge_records", []) if r["status"] in {"pending_entry", "tracking"})
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
