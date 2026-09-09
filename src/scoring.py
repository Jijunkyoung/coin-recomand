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
    technical_points = 0
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
    community_mentions = metrics.get("community_mentions") or {}
    community_total = metrics.get("community_total") or 0
    community_sources = metrics.get("community_sources") or 0
    development = metrics.get("development") or {}
    tokenomics = metrics.get("tokenomics") or {}
    unlock = tokenomics.get("next_unlock") or {}

    if ema20 and ema50 and price > ema20 > ema50:
        technical_points += 8
        reasons.append("가격·EMA20·EMA50이 정배열입니다.")
    elif ema20 and ema50 and price < ema20 < ema50:
        technical_points -= 10
        risks.append("중기 이동평균선이 역배열입니다.")
    if rsi_value is not None:
        if 45 <= rsi_value <= 65:
            technical_points += 4
            reasons.append(f"RSI {rsi_value:.1f}로 추세와 과열 부담의 균형이 좋습니다.")
        elif rsi_value >= 75:
            technical_points -= 7
            risks.append(f"RSI {rsi_value:.1f}로 과매수 위험이 있습니다.")
        elif rsi_value < 35:
            technical_points -= 3
            risks.append(f"RSI {rsi_value:.1f}로 하락 추세 지속 여부를 확인해야 합니다.")
    if histogram is not None:
        if histogram > 0:
            technical_points += 4
            reasons.append("MACD 모멘텀이 양수입니다.")
        else:
            technical_points -= 3
            risks.append("MACD 모멘텀이 약세입니다.")
    if return7 is not None and return30 is not None:
        if 0 < return7 <= 15 and 3 < return30 <= 35:
            technical_points += 6
            reasons.append(f"7일 {return7:.1f}%·30일 {return30:.1f}%로 완만한 상승 흐름입니다.")
        if return7 > 25 or return30 > 60:
            technical_points -= 8
            risks.append("최근 급등폭이 커 추격매수 위험이 있습니다.")
    score += max(-18, min(22, technical_points))
    if volume is not None:
        if 1.1 <= volume <= 3:
            score += 5
            reasons.append(f"최근 거래량이 30일 평균의 {volume:.2f}배로 증가했습니다.")
        elif volume < 0.65:
            score -= 4
            risks.append("최근 거래량이 장기 평균보다 크게 낮습니다.")
    if trending_rank is not None:
        score += max(1, 4 - (trending_rank - 1) // 3)
        reasons.append(f"CoinGecko 24시간 인기 검색 {trending_rank}위입니다.")
    if community_total:
        mentioned_sources = sum(1 for value in community_mentions.values() if value)
        exposure_rate = metrics.get("community_exposure_rate") or 0
        community_points = min(5, 1 + int(community_total >= 3) + int(community_total >= 7) + max(0, mentioned_sources - 1) + int(exposure_rate >= 3))
        score += community_points
        source_labels = {"reddit": "Reddit", "dcinside": "디시", "coinpan": "코인판"}
        breakdown = "·".join(f"{source_labels.get(name, name)} {value}회" for name, value in community_mentions.items() if value is not None)
        reasons.append(f"오늘 커뮤니티 표본 {community_sources}곳에서 총 {community_total}회 언급됐습니다({breakdown}).")
    commits = development.get("commits_30d")
    release_days = development.get("latest_release_days")
    commit_days = development.get("latest_commit_days")
    development_points = 0
    if commits is not None:
        if commits >= 20:
            development_points += 3
            reasons.append(f"공식 GitHub에서 최근 30일 {commits}건의 커밋이 확인돼 개발 활동이 활발합니다.")
        elif commits >= 5:
            development_points += 2
            reasons.append(f"공식 GitHub에서 최근 30일 {commits}건의 개발 커밋이 확인됐습니다.")
        elif commits == 0 and commit_days is not None and commit_days >= 120:
            score -= 5
            risks.append(f"공식 GitHub의 마지막 커밋이 {commit_days}일 전으로 개발 정체 여부를 확인해야 합니다.")
    if release_days is not None and release_days <= 45:
        development_points += 2
        release_name = development.get("latest_release_name") or "신규 버전"
        reasons.append(f"{release_days}일 전 공식 GitHub에 {release_name} 릴리스가 게시됐습니다.")
    score += min(4, development_points)
    circulating_ratio = tokenomics.get("circulating_ratio")
    if circulating_ratio is not None:
        if circulating_ratio < 35:
            score -= 6
            risks.append(f"총공급량 대비 유통 비율이 {circulating_ratio:.1f}%로 장기 희석 위험이 큽니다.")
        elif circulating_ratio < 55:
            score -= 4
            risks.append(f"총공급량 대비 유통 비율이 {circulating_ratio:.1f}%로 추가 공급 부담을 확인해야 합니다.")
        elif circulating_ratio >= 85:
            score += 2
            reasons.append(f"총공급량의 {circulating_ratio:.1f}%가 유통돼 잠재 희석 부담이 비교적 낮습니다.")
    unlock_days = unlock.get("days_until")
    if unlock_days is not None and unlock_days <= 60:
        unlock_ratio = unlock.get("percent_circulating")
        if unlock_days <= 30 and unlock_ratio is not None and unlock_ratio >= 5:
            score -= 14
        elif unlock_days <= 30 and unlock_ratio is not None and unlock_ratio >= 1:
            score -= 9
        elif unlock_days <= 7:
            score -= 8
        elif unlock_days <= 30:
            score -= 6
        elif unlock_ratio is not None and unlock_ratio >= 5:
            score -= 10
        else:
            score -= 4
        ratio_text = f"(유통량의 {unlock_ratio:.2f}%)" if unlock_ratio is not None else ""
        risks.append(f"{unlock_days}일 후 토큰 언락이 예정돼 공급 증가 가능성이 있습니다{ratio_text}.")
    project_notice = tokenomics.get("project_notice")
    if project_notice:
        risks.append(f"프로젝트 공지 확인 필요: {project_notice}")
    if volatility is not None and volatility > 120:
        score -= 8
        risks.append(f"30일 연환산 변동성 {volatility:.0f}%로 가격 진폭이 큽니다.")
    if regime == "하락":
        score -= 20
        risks.insert(0, "비트코인 시장 국면이 하락으로 판정됐습니다.")
    elif regime == "중립":
        score -= 4
    return max(0, min(100, round(score))), reasons, risks


def recommendation_label(score: int, regime: str) -> str:
    if regime == "하락":
        return "관찰" if score >= 55 else "보류"
    threshold = 72 if regime == "중립" else 67
    if score >= threshold:
        return "분할매수 후보"
    return "관찰" if score >= 52 else "보류"
