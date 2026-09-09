from __future__ import annotations

from typing import Any


def market_regime(metrics: dict[str, Any]) -> tuple[int, str, list[str]]:
    score = 50
    reasons: list[str] = []
    price = metrics.get("price") or 0
    ema20 = metrics.get("ema20")
    ema50 = metrics.get("ema50")
    return30 = metrics.get("return_30d")
    volume = metrics.get("volume_ratio")
    mvrv = metrics.get("mvrv_z")
    fear = metrics.get("fear_greed")

    if ema20 and ema50:
        if price > ema20 > ema50:
            score += 18
            reasons.append("가격이 EMA20·EMA50 위에 있어 중기 상승 추세입니다.")
        elif price < ema20 < ema50:
            score -= 20
            reasons.append("가격이 EMA20·EMA50 아래라 중기 하락 추세입니다.")
        else:
            reasons.append("이동평균선이 엇갈려 방향 확인이 필요합니다.")
    if return30 is not None:
        if 3 <= return30 <= 25:
            score += 10
            reasons.append(f"30일 수익률 {return30:.1f}%로 상승 모멘텀이 유지됩니다.")
        elif return30 < -10:
            score -= 12
            reasons.append(f"30일 수익률 {return30:.1f}%로 하락 압력이 큽니다.")
        elif return30 > 35:
            score -= 5
            reasons.append(f"30일 {return30:.1f}% 급등으로 단기 과열 가능성이 있습니다.")
    if volume is not None:
        if volume >= 1.2:
            score += 8
            reasons.append(f"최근 7일 거래량이 30일 평균의 {volume:.2f}배입니다.")
        elif volume < 0.7:
            score -= 5
            reasons.append("상승을 확인할 거래량이 부족합니다.")
    if mvrv is not None:
        if mvrv < 0:
            score += 15
            reasons.append(f"MVRV Z-Score {mvrv:.2f}로 역사적 저평가 구간입니다.")
        elif mvrv < 1:
            score += 8
            reasons.append(f"MVRV Z-Score {mvrv:.2f}로 과열 부담이 낮습니다.")
        elif mvrv >= 5:
            score -= 15
            reasons.append(f"MVRV Z-Score {mvrv:.2f}로 고평가 위험이 커졌습니다.")
    if fear is not None:
        if fear <= 25:
            score += 5
            reasons.append(f"공포·탐욕 지수 {fear}로 극단적 공포 구간입니다.")
        elif fear >= 80:
            score -= 8
            reasons.append(f"공포·탐욕 지수 {fear}로 과도한 탐욕 구간입니다.")

    score = max(0, min(100, round(score)))
    regime = "상승" if score >= 65 else "하락" if score < 42 else "중립"
    return score, regime, reasons


def alt_score(metrics: dict[str, Any], regime: str) -> tuple[int, list[str], list[str]]:
    score = 35
    reasons: list[str] = []
    risks: list[str] = []
    price = metrics.get("price") or 0
    ema20 = metrics.get("ema20")
    ema50 = metrics.get("ema50")
    rsi_value = metrics.get("rsi")
    histogram = metrics.get("macd_histogram")
    return7 = metrics.get("return_7d")
    return30 = metrics.get("return_30d")
    volume = metrics.get("volume_ratio")
    volatility = metrics.get("volatility")
    trending_rank = metrics.get("trending_rank")
    mentions = metrics.get("reddit_mentions") or 0

    if ema20 and ema50 and price > ema20 > ema50:
        score += 18
        reasons.append("가격·EMA20·EMA50이 정배열입니다.")
    elif ema20 and ema50 and price < ema20 < ema50:
        score -= 18
        risks.append("중기 이동평균선이 역배열입니다.")
    if rsi_value is not None:
        if 45 <= rsi_value <= 65:
            score += 12
            reasons.append(f"RSI {rsi_value:.1f}로 추세와 과열 부담의 균형이 좋습니다.")
        elif rsi_value >= 75:
            score -= 12
            risks.append(f"RSI {rsi_value:.1f}로 과매수 위험이 있습니다.")
        elif rsi_value < 35:
            score -= 5
            risks.append(f"RSI {rsi_value:.1f}로 하락 추세 지속 여부를 확인해야 합니다.")
    if histogram is not None:
        if histogram > 0:
            score += 8
            reasons.append("MACD 모멘텀이 양수입니다.")
        else:
            score -= 5
            risks.append("MACD 모멘텀이 약세입니다.")
    if return7 is not None and return30 is not None:
        if 0 < return7 <= 15 and 3 < return30 <= 35:
            score += 12
            reasons.append(f"7일 {return7:.1f}%·30일 {return30:.1f}%로 완만한 상승 흐름입니다.")
        if return7 > 25 or return30 > 60:
            score -= 15
            risks.append("최근 급등폭이 커 추격매수 위험이 있습니다.")
    if volume is not None:
        if 1.1 <= volume <= 3:
            score += 10
            reasons.append(f"최근 거래량이 30일 평균의 {volume:.2f}배로 증가했습니다.")
        elif volume < 0.65:
            score -= 6
            risks.append("최근 거래량이 장기 평균보다 크게 낮습니다.")
    if trending_rank is not None:
        score += max(2, 11 - trending_rank)
        reasons.append(f"CoinGecko 24시간 인기 검색 {trending_rank}위입니다.")
    if mentions:
        score += min(8, mentions * 2)
        reasons.append(f"Reddit 최근 24시간 표본에서 {mentions}회 언급됐습니다.")
    if volatility is not None and volatility > 120:
        score -= 8
        risks.append(f"30일 연환산 변동성 {volatility:.0f}%로 가격 진폭이 큽니다.")
    if regime == "하락":
        score -= 25
        risks.insert(0, "비트코인 시장 국면이 하락으로 판정됐습니다.")
    elif regime == "중립":
        score -= 5
    return max(0, min(100, round(score))), reasons, risks


def recommendation_label(score: int, regime: str) -> str:
    if regime == "하락":
        return "관찰" if score >= 55 else "보류"
    threshold = 72 if regime == "중립" else 67
    if score >= threshold:
        return "분할매수 후보"
    return "관찰" if score >= 52 else "보류"
