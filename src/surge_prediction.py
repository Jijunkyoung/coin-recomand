"""Cross-sectional 24-hour surge research model.

The model is intentionally small and dependency-free.  It learns only from
features that were observable at each historical candle, keeps the newest
dates as an out-of-time validation set, and never places an order.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

from .major_events import negative_event_risk


FEATURES = (
    "return_1d",
    "return_3d",
    "return_7d",
    "volume_ratio",
    "volume_acceleration",
    "daily_range",
    "close_position",
    "breakout_gap",
    "bollinger_width",
    "rsi_centered",
    "atr_ratio",
    "btc_return_1d",
    "relative_7d",
    "log_turnover",
)

FEATURE_LABELS = {
    "return_1d": "직전 1일 가격 흐름",
    "return_3d": "3일 가격 가속도",
    "return_7d": "7일 추세",
    "volume_ratio": "20일 대비 거래대금",
    "volume_acceleration": "최근 거래대금 가속",
    "daily_range": "당일 가격 변동폭",
    "close_position": "일중 종가 위치",
    "breakout_gap": "20일 고점 돌파 거리",
    "bollinger_width": "볼린저밴드 폭",
    "rsi_centered": "RSI 균형",
    "atr_ratio": "평균 진폭",
    "btc_return_1d": "비트코인 당일 흐름",
    "relative_7d": "BTC 대비 7일 상대강도",
    "log_turnover": "거래대금 규모",
}

MIN_LOOKBACK = 30
SURGE_RETURN = 0.10
SURGE_VOLUME_RATIO = 1.5
SURGE_EXCESS_BTC = 0.07


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_row(row: dict[str, Any]) -> dict[str, float | str] | None:
    try:
        close = float(row["price"])
        high = float(row.get("high", close))
        low = float(row.get("low", close))
        volume = float(row["volume"])
        date = str(row["date"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(close, high, low) <= 0 or volume < 0 or not date:
        return None
    return {"date": date, "close": close, "high": max(high, close), "low": min(low, close), "volume": volume}


def _clean_history(history: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    rows = [_safe_row(row) for row in history]
    return sorted((row for row in rows if row is not None), key=lambda row: str(row["date"]))


def _rsi(closes: list[float], end: int, period: int = 14) -> float:
    changes = [closes[index] - closes[index - 1] for index in range(end - period + 1, end + 1)]
    gains = mean(max(change, 0) for change in changes)
    losses = mean(max(-change, 0) for change in changes)
    if losses == 0:
        return 100.0
    return 100 - 100 / (1 + gains / losses)


def _btc_context(history: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    rows = _clean_history(history)
    closes = [float(row["close"]) for row in rows]
    result: dict[str, dict[str, float]] = {}
    for index in range(7, len(rows)):
        result[str(rows[index]["date"])] = {
            "return_1d": closes[index] / closes[index - 1] - 1,
            "return_7d": closes[index] / closes[index - 7] - 1,
            "next_high_return": (
                float(rows[index + 1]["high"]) / closes[index] - 1 if index + 1 < len(rows) else 0.0
            ),
        }
    return result


def feature_snapshot(
    rows: list[dict[str, float | str]],
    index: int,
    btc: dict[str, dict[str, float]],
) -> tuple[list[float], dict[str, float]] | None:
    """Build a point-in-time vector using rows at or before ``index`` only."""
    if index < MIN_LOOKBACK or index >= len(rows):
        return None
    date = str(rows[index]["date"])
    btc_row = btc.get(date)
    if not btc_row:
        return None
    closes = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    close = closes[index]
    prior20 = closes[index - 20:index]
    prior_volumes = volumes[index - 20:index]
    if not prior20 or mean(prior_volumes) <= 0:
        return None
    recent20 = closes[index - 19:index + 1]
    band_mean = mean(recent20)
    ranges = []
    for cursor in range(index - 13, index + 1):
        high = float(rows[cursor]["high"])
        low = float(rows[cursor]["low"])
        previous = closes[cursor - 1]
        ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    high = float(rows[index]["high"])
    low = float(rows[index]["low"])
    span = max(high - low, close * 1e-9)
    coin_return_7d = close / closes[index - 7] - 1
    values = {
        "return_1d": _clip(close / closes[index - 1] - 1, -0.5, 0.5),
        "return_3d": _clip(close / closes[index - 3] - 1, -0.8, 0.8),
        "return_7d": _clip(coin_return_7d, -1.0, 1.0),
        "volume_ratio": _clip(volumes[index] / mean(prior_volumes), 0.0, 8.0),
        "volume_acceleration": _clip(
            mean(volumes[index - 2:index + 1]) / mean(volumes[index - 9:index - 2]), 0.0, 8.0
        ),
        "daily_range": _clip((high - low) / close, 0.0, 1.0),
        "close_position": _clip((close - low) / span - 0.5, -0.5, 0.5),
        "breakout_gap": _clip(close / max(prior20) - 1, -0.6, 0.6),
        "bollinger_width": _clip(4 * pstdev(recent20) / band_mean if band_mean else 0.0, 0.0, 1.5),
        "rsi_centered": _clip((_rsi(closes, index) - 50) / 50, -1.0, 1.0),
        "atr_ratio": _clip(mean(ranges) / close, 0.0, 1.0),
        "btc_return_1d": _clip(btc_row["return_1d"], -0.3, 0.3),
        "relative_7d": _clip(coin_return_7d - btc_row["return_7d"], -1.0, 1.0),
        "log_turnover": _clip(math.log1p(volumes[index] / 1_000_000_000) / 10, 0.0, 2.0),
    }
    return [values[name] for name in FEATURES], values


def surge_label(
    rows: list[dict[str, float | str]],
    index: int,
    btc: dict[str, dict[str, float]],
) -> int | None:
    if index + 1 >= len(rows):
        return None
    date = str(rows[index]["date"])
    btc_row = btc.get(date)
    if not btc_row:
        return None
    close = float(rows[index]["close"])
    future = rows[index + 1]
    prior_volume = mean(float(row["volume"]) for row in rows[index - 19:index + 1])
    if prior_volume <= 0:
        return None
    future_return = float(future["high"]) / close - 1
    future_volume_ratio = float(future["volume"]) / prior_volume
    excess = future_return - btc_row["next_high_return"]
    return int(
        future_return >= SURGE_RETURN
        and future_volume_ratio >= SURGE_VOLUME_RATIO
        and excess >= SURGE_EXCESS_BTC
    )


def build_samples(coins: list[dict[str, Any]], bitcoin_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    btc = _btc_context(bitcoin_history)
    samples: list[dict[str, Any]] = []
    for coin in coins:
        rows = _clean_history(coin.get("history") or [])
        # Upbit's last daily candle is the still-open KST session.  Never use it
        # as a completed future label; keep one additional closed day between
        # the training target and the live prediction snapshot.
        for index in range(MIN_LOOKBACK, len(rows) - 2):
            snapshot = feature_snapshot(rows, index, btc)
            label = surge_label(rows, index, btc)
            if snapshot is None or label is None:
                continue
            samples.append({
                "date": str(rows[index]["date"]),
                "market": coin.get("market"),
                "x": snapshot[0],
                "y": label,
            })
    return sorted(samples, key=lambda row: (row["date"], str(row["market"])))


def _standardize(rows: list[list[float]]) -> tuple[list[float], list[float]]:
    means = [mean(row[index] for row in rows) for index in range(len(FEATURES))]
    scales = [pstdev(row[index] for row in rows) or 1.0 for index in range(len(FEATURES))]
    return means, scales


def _normalize(row: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [(value - center) / scale for value, center, scale in zip(row, means, scales)]


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-_clip(value, -30, 30)))


def _fit(rows: list[dict[str, Any]], epochs: int = 260) -> dict[str, Any]:
    xs = [row["x"] for row in rows]
    ys = [int(row["y"]) for row in rows]
    centers, scales = _standardize(xs)
    normalized = [_normalize(row, centers, scales) for row in xs]
    positives = sum(ys)
    negatives = len(ys) - positives
    positive_weight = min(12.0, negatives / positives) if positives else 1.0
    weights = [0.0] * len(FEATURES)
    intercept = 0.0
    for epoch in range(epochs):
        gradient = [0.0] * len(weights)
        intercept_gradient = 0.0
        total_weight = 0.0
        for x, y in zip(normalized, ys):
            sample_weight = positive_weight if y else 1.0
            error = (_sigmoid(intercept + sum(a * b for a, b in zip(weights, x))) - y) * sample_weight
            intercept_gradient += error
            for index, value in enumerate(x):
                gradient[index] += error * value
            total_weight += sample_weight
        rate = 0.18 / (1 + epoch / 180)
        intercept -= rate * intercept_gradient / total_weight
        for index in range(len(weights)):
            weights[index] -= rate * (gradient[index] / total_weight + 0.015 * weights[index])
    raw = [intercept + sum(a * b for a, b in zip(weights, x)) for x in normalized]
    target_rate = max(1e-5, min(1 - 1e-5, positives / len(rows)))
    low, high = -20.0, 20.0
    for _ in range(80):
        midpoint = (low + high) / 2
        if mean(_sigmoid(value + midpoint) for value in raw) > target_rate:
            high = midpoint
        else:
            low = midpoint
    return {
        "weights": weights,
        "intercept": intercept,
        "calibration_offset": (low + high) / 2,
        "centers": centers,
        "scales": scales,
    }


def _predict(model: dict[str, Any], row: list[float]) -> tuple[float, list[float]]:
    normalized = _normalize(row, model["centers"], model["scales"])
    contributions = [weight * value for weight, value in zip(model["weights"], normalized)]
    score = model["intercept"] + sum(contributions) + model["calibration_offset"]
    return _sigmoid(score), contributions


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positive_scores = [score for score, label in zip(scores, labels) if label]
    negative_scores = [score for score, label in zip(scores, labels) if not label]
    if not positive_scores or not negative_scores:
        return None
    wins = 0.0
    for positive in positive_scores:
        for negative in negative_scores:
            wins += 1 if positive > negative else 0.5 if positive == negative else 0
    return wins / (len(positive_scores) * len(negative_scores))


def _validate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    dates = sorted({row["date"] for row in samples})
    split_index = max(1, int(len(dates) * 0.8))
    split_date = dates[min(split_index, len(dates) - 1)]
    train_rows = [row for row in samples if row["date"] < split_date]
    validation_rows = [row for row in samples if row["date"] >= split_date]
    if len(train_rows) < 200 or sum(row["y"] for row in train_rows) < 5 or not validation_rows:
        return {"split_date": split_date, "samples": len(validation_rows), "auc": None, "precision_top_10pct": None}
    model = _fit(train_rows)
    predictions = [_predict(model, row["x"])[0] for row in validation_rows]
    labels = [int(row["y"]) for row in validation_rows]
    selected_count = max(1, math.ceil(len(validation_rows) * 0.1))
    selected = sorted(zip(predictions, labels), reverse=True)[:selected_count]
    return {
        "split_date": split_date,
        "samples": len(validation_rows),
        "positives": sum(labels),
        "base_rate_pct": round(mean(labels) * 100, 2),
        "auc": round(_auc(labels, predictions), 3) if _auc(labels, predictions) is not None else None,
        "precision_top_10pct": round(mean(label for _, label in selected) * 100, 2),
    }


def _development_signal(coin: dict[str, Any]) -> str | None:
    development = coin.get("development") or {}
    commits = development.get("commits_30d")
    release_days = development.get("latest_release_days")
    if _finite(release_days) and release_days <= 30:
        name = development.get("latest_release_name")
        return f"{int(release_days)}일 전 공식 릴리스{name and f'({name})' or ''}"
    if _finite(commits) and commits >= 20:
        return f"공식 GitHub 30일 커밋 {int(commits)}건"
    if development.get("status") in {"정체 확인", "낮은 활동"}:
        return f"개발활동 {development['status']}"
    return None


def _candidate_row(
    coin: dict[str, Any],
    model: dict[str, Any],
    btc: dict[str, dict[str, float]],
    major_events: list[dict[str, Any]],
    forward_feedback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    rows = _clean_history(coin.get("history") or [])
    if not rows:
        return None
    snapshot = feature_snapshot(rows, len(rows) - 1, btc)
    if snapshot is None:
        return None
    probability, contributions = _predict(model, snapshot[0])
    ranked = sorted(zip(contributions, FEATURES), reverse=True)
    reasons = [FEATURE_LABELS[name] for contribution, name in ranked if contribution > 0][:3]
    values = snapshot[1]
    risks: list[str] = []
    return_1d = values["return_1d"] * 100
    if return_1d >= 10:
        risks.append(f"이미 하루 {return_1d:.1f}% 상승해 추격 위험이 큽니다.")
    if coin.get("rsi") is not None and float(coin["rsi"]) >= 72:
        risks.append(f"RSI {float(coin['rsi']):.1f}로 단기 과열 구간입니다.")
    if values["volume_ratio"] >= 5:
        risks.append(f"거래대금이 20일 평균의 {values['volume_ratio']:.1f}배로 급증했습니다.")
    development = _development_signal(coin)
    related = [
        {
            "title": event.get("title"),
            "importance": event.get("importance") or event.get("impact") or "보통",
            "impact": event.get("impact") or "중립·혼재",
            "score_penalty": event.get("score_penalty") or 0,
            "source_url": event.get("source_url") or event.get("url"),
        }
        for event in major_events
        if coin.get("symbol") in (event.get("related_symbols") or [])
    ][:2]
    event_risk = negative_event_risk(str(coin.get("symbol") or ""), major_events)
    if event_risk["penalty"]:
        risks = [
            f"🚨 [악재] {event.get('title')} (중요도 {event.get('importance', '보통')} · -{event['score_penalty']}점)"
            for event in event_risk["events"][:2]
        ] + risks
    adjustments = (forward_feedback or {}).get("reason_adjustments") or {}
    matched_adjustments = [(reason, adjustments[reason]) for reason in reasons if reason in adjustments]
    feedback_adjustment = mean(value for _, value in matched_adjustments) if matched_adjustments else 0.0
    feedback_adjustment = _clip(feedback_adjustment, -5.0, 5.0)
    adjusted_score = _clip(probability * 100 + feedback_adjustment - event_risk["penalty"], 0.0, 100.0)
    performance = (forward_feedback or {}).get("reason_performance") or {}
    feedback_evidence = [
        {
            "signal": reason,
            "samples": performance[reason].get("samples", 0),
            "hits": performance[reason].get("hits", 0),
            "hit_rate_pct": performance[reason].get("hit_rate_pct"),
            "adjustment": performance[reason].get("adjustment", 0.0),
        }
        for reason in reasons if reason in performance
    ]
    return {
        "market": coin.get("market"),
        "symbol": coin.get("symbol"),
        "name": coin.get("name"),
        "price": coin.get("price"),
        "model_probability_pct": round(probability * 100, 1),
        "signal_score": round(adjusted_score, 1),
        "feedback_adjusted_score": round(adjusted_score, 1),
        "feedback_adjustment_pct_points": round(feedback_adjustment, 2),
        "feedback_notes": [
            f"{item['signal']} · {item['samples']}건 중 {item['hits']}건 10% 도달"
            f" · {item['adjustment']:+.2f}점"
            for item in feedback_evidence
        ],
        "feedback_evidence": feedback_evidence,
        "event_risk_penalty": event_risk["penalty"],
        "reasons": reasons or ["복합 기술신호"],
        "risks": risks,
        "watch_status": "악재 주의" if event_risk["penalty"] else "추격 주의" if risks and return_1d >= 10 else "관찰 후보",
        "volume_ratio_20d": round(values["volume_ratio"], 2),
        "relative_7d_pct": round(values["relative_7d"] * 100, 2),
        "return_1d_pct": round(return_1d, 2),
        "rsi": round(float(coin["rsi"]), 2) if _finite(coin.get("rsi")) else None,
        "development_signal": development,
        "related_events": related,
        "trade_value_24h": coin.get("trade_value_24h"),
    }


def _final_recommendations(
    candidates: list[dict[str, Any]],
    forward_feedback: dict[str, Any] | None,
    model_confidence: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the current top-three shortlist without leaking later outcomes."""
    feedback = forward_feedback or {}
    completed = int(feedback.get("completed") or 0)
    minimum = int(feedback.get("minimum_for_adjustment") or 20)
    learning_applied = completed >= minimum
    eligible = [
        candidate for candidate in candidates
        if (candidate.get("event_risk_penalty") or 0) < 12
        and (candidate.get("return_1d_pct") is None or candidate["return_1d_pct"] < 15)
        and (candidate.get("rsi") is None or candidate["rsi"] < 78)
    ]
    picks = []
    for rank, candidate in enumerate(eligible[:3], start=1):
        evidence = candidate.get("feedback_evidence") or []
        learned_signals = [item for item in evidence if item.get("samples", 0) >= 5]
        candidate_confidence = (
            "보통" if learning_applied and learned_signals and model_confidence in {"보통", "높음"}
            else "낮음"
        )
        picks.append({
            **candidate,
            "final_rank": rank,
            "final_score": candidate.get("feedback_adjusted_score", candidate.get("signal_score")),
            "learning_applied": learning_applied,
            "recommendation_confidence": candidate_confidence,
            "selection_summary": " · ".join((candidate.get("reasons") or ["복합 기술신호"])[:2]),
        })
    status = (
        "최종 추천·추적학습 반영" if learning_applied and picks
        else "예비 추천·추적학습 대기" if picks
        else "현재 위험필터 통과 후보 없음"
    )
    return picks, {
        "status": status,
        "learning_applied": learning_applied,
        "completed": completed,
        "minimum_for_adjustment": minimum,
        "selection_count": len(picks),
        "rule": "위험반영 점수 순 · 중요 악재 12점 이상 제외 · 1일 15% 이상/RSI 78 이상 추격 제외",
    }


def build_surge_research(
    coins: list[dict[str, Any]],
    bitcoin_history: list[dict[str, Any]],
    major_events: list[dict[str, Any]] | None = None,
    forward_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    samples = build_samples(coins, bitcoin_history)
    dates = {row["date"] for row in samples}
    positives = sum(row["y"] for row in samples)
    base = {
        "status": "학습 자료 부족",
        "model": "정규화 로지스틱 회귀",
        "target": "다음 24시간 고가 +10%·거래대금 1.5배·BTC 대비 +7%p를 모두 충족",
        "samples": len(samples),
        "positive_samples": positives,
        "observed_days": len(dates),
        "validation": None,
        "forward_feedback": {
            key: (forward_feedback or {}).get(key)
            for key in ("status", "completed", "hits", "hit_rate_pct", "minimum_for_adjustment", "reason_performance")
        },
        "final_recommendations": [],
        "final_selection": {
            "status": "학습 자료 부족", "learning_applied": False,
            "completed": (forward_feedback or {}).get("completed", 0),
            "minimum_for_adjustment": (forward_feedback or {}).get("minimum_for_adjustment", 20),
            "selection_count": 0,
        },
        "candidates": [],
        "limitations": [
            "급등 가능성은 통계적 연구 점수이며 매수 성공 확률이나 수익을 보장하지 않습니다.",
            "일봉 기반이므로 장중 급등 후 급락과 실제 체결 가능성을 완전히 반영하지 못합니다.",
            "개발·뉴스 신호는 과거 시점 데이터 누락으로 가격모델 학습에는 넣지 않습니다. 현재 직접 관련된 악재만 중요도별 4·8·12점, 합계 최대 16점 감점합니다.",
            "추적 결과는 전략 연구실의 최종 급등 예상 순위에만 반영하며 기본 매수 추천·메일·실제 주문에는 반영하지 않습니다.",
        ],
    }
    if len(samples) < 400 or positives < 12 or len(dates) < 60:
        return base
    validation = _validate(samples)
    model = _fit(samples)
    btc = _btc_context(bitcoin_history)
    candidates = [
        row for row in (
            _candidate_row(coin, model, btc, major_events or [], forward_feedback) for coin in coins
        ) if row is not None
    ]
    candidates.sort(key=lambda row: (row["feedback_adjusted_score"], row["model_probability_pct"], row.get("trade_value_24h") or 0), reverse=True)
    auc = validation.get("auc")
    confidence = "높음" if len(samples) >= 2500 and positives >= 40 and auc is not None and auc >= 0.65 else "보통" if auc is not None else "낮음"
    final_recommendations, final_selection = _final_recommendations(candidates, forward_feedback, confidence)
    base.update({
        "status": "실험 학습 완료·수익성 미검증",
        "confidence": confidence,
        "validation": validation,
        "candidates": candidates[:10],
        "final_recommendations": final_recommendations,
        "final_selection": final_selection,
        "feature_names": [FEATURE_LABELS[name] for name in FEATURES],
    })
    return base
