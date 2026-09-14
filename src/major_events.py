from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


KST = timezone(timedelta(hours=9))
IMPORTANCE_ORDER = {"매우 높음": 0, "높음": 1, "보통": 2}

EVENT_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("법안·규제", ("clarity", "클래리티", "법안", "표결", "투표", "의회", "규제", "sec", "판결")),
    ("통화정책", ("fomc", "연준", "금리 결정", "금리결정", "파월")),
    ("경제지표", ("cpi", "소비자물가", "고용보고서", "비농업", "실업률", "ppi", "gdp")),
    ("ETF·기관", ("etf", "현물 승인", "승인 결정", "기관")),
    ("토크노믹스", ("언락", "unlock", "락업", "토큰 해제")),
    ("네트워크", ("메인넷", "하드포크", "업그레이드", "mainnet", "hard fork")),
    ("거래소", ("상장폐지", "상장", "거래지원", "listing")),
)

CRITICAL_TERMS = (
    "clarity", "클래리티", "법안 표결", "법안 투표", "fomc", "금리 결정", "금리결정",
    "cpi", "소비자물가", "etf 승인", "etf 결정", "sec 판결", "대규모 언락",
)
HIGH_TERMS = ("법안", "표결", "투표", "규제", "고용보고서", "비농업", "ppi", "gdp", "언락", "하드포크", "메인넷")
SCHEDULE_TERMS = ("예정", "일정", "이번 주", "이번주", "내일", "모레", "표결", "투표", "발표", "결정", "회의", "마감")
WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def load_manual_events(path: str | Path = "config/major_events.json") -> list[dict[str, Any]]:
    event_path = Path(path)
    if not event_path.exists():
        return []
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    rows = payload.get("events", []) if isinstance(payload, dict) else payload
    return [dict(row) for row in rows if isinstance(row, dict)]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _event_type(text: str) -> str:
    lowered = text.lower()
    return next((name for name, terms in EVENT_TYPES if any(term in lowered for term in terms)), "시장 일정")


def _importance(text: str, supplied: Any = None) -> str:
    if supplied in IMPORTANCE_ORDER:
        return str(supplied)
    lowered = text.lower()
    if any(term in lowered for term in CRITICAL_TERMS):
        return "매우 높음"
    if any(term in lowered for term in HIGH_TERMS):
        return "높음"
    return "보통"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None


def _date_from_headline(title: str, today: date) -> date | None:
    match = re.search(r"(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})일?", title)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    match = re.search(r"(?<!\d)(\d{1,2})월\s*(\d{1,2})일", title)
    if match:
        try:
            candidate = date(today.year, int(match.group(1)), int(match.group(2)))
            return candidate if candidate >= today - timedelta(days=7) else candidate.replace(year=today.year + 1)
        except ValueError:
            return None
    if "모레" in title:
        return today + timedelta(days=2)
    if "내일" in title:
        return today + timedelta(days=1)
    weekday_match = re.search(r"(?:이번\s*주\s*)?([월화수목금토일])요일", title)
    if weekday_match:
        target = WEEKDAYS[weekday_match.group(1)]
        days = (target - today.weekday()) % 7
        return today + timedelta(days=days)
    return None


def _scenarios(event_type: str) -> tuple[str, str]:
    scenarios = {
        "법안·규제": ("시장 규칙의 불확실성 완화와 기관 참여 확대 가능", "부결·지연·규제 강화 시 위험자산 변동성 확대 가능"),
        "통화정책": ("완화적 결정·발언이면 위험자산 유동성 기대 개선", "매파적 결정·발언이면 달러 강세와 코인 조정 가능"),
        "경제지표": ("물가·고용 둔화가 확인되면 금리 부담 완화 가능", "예상보다 강한 지표면 금리 인하 기대 후퇴 가능"),
        "ETF·기관": ("승인·자금 유입 확인 시 현물 수요 확대 가능", "거절·연기 또는 유출 확대 시 투자심리 약화 가능"),
        "토크노믹스": ("예상보다 작은 매도 물량이면 공급 부담 완화", "대규모 물량 출회 시 단기 가격 압력 가능"),
        "네트워크": ("정상 출시·업그레이드 시 사용성과 신뢰 개선", "지연·오류 발생 시 관련 자산 신뢰 약화 가능"),
        "거래소": ("유동성 확대와 신규 수요 유입 가능", "상장폐지·지원 축소 시 유동성 급감 가능"),
    }
    return scenarios.get(event_type, ("긍정적 결과면 시장심리 개선 가능", "부정적 결과면 단기 변동성 확대 가능"))


def _normalize_event(row: dict[str, Any], today: date, origin: str) -> dict[str, Any] | None:
    title = _clean(row.get("title"))
    if not title:
        return None
    event_date = _parse_date(row.get("date"))
    if event_date is None and origin == "news":
        event_date = _date_from_headline(title, today)
    event_type = _clean(row.get("event_type")) or _event_type(" ".join([title, *map(str, row.get("categories") or [])]))
    importance = _importance(title, row.get("importance"))
    bull_case, bear_case = _scenarios(event_type)
    days_until = (event_date - today).days if event_date else None
    status = _clean(row.get("status")) or ("예정" if origin != "news" and event_date else "확인 필요")
    if status not in {"예정", "확정", "확인 필요", "연기", "완료", "취소"}:
        status = "확인 필요"
    if event_date and event_date < today and status not in {"완료", "취소", "연기"}:
        status = "확인 필요"
    source_url = _clean(row.get("source_url") or row.get("url"))
    symbols = sorted({str(symbol).upper() for symbol in row.get("related_symbols") or [] if symbol})
    identifier = _clean(row.get("id")) or re.sub(r"[^0-9a-z가-힣]+", "-", title.lower()).strip("-")[:80]
    return {
        "id": identifier,
        "title": title[:220],
        "event_type": event_type,
        "importance": importance,
        "status": status,
        "verification": _clean(row.get("verification")) or ("고정 등록" if origin == "manual" else "공식 일정 확인 필요" if origin == "news" else "외부 일정 참고"),
        "date": event_date.isoformat() if event_date else None,
        "date_kst": event_date.strftime("%m-%d") if event_date else "일정 확인 중",
        "time_kst": _clean(row.get("time_kst")) or None,
        "days_until": days_until,
        "related_symbols": symbols or (["BTC", "ETH"] if event_type in {"법안·규제", "통화정책", "경제지표", "ETF·기관"} else []),
        "summary": _clean(row.get("summary")) or (title if origin == "news" else f"{event_type} 관련 시장 영향 일정을 추적합니다."),
        "bull_case": _clean(row.get("bull_case")) or bull_case,
        "bear_case": _clean(row.get("bear_case")) or bear_case,
        "source": _clean(row.get("source")) or ("Google News 후보" if origin == "news" else "CoinMarketCal"),
        "source_url": source_url,
        "official_source": bool(row.get("official_source")),
        "origin": origin,
        "last_verified": _clean(row.get("last_verified")) or None,
    }


def build_major_events(
    upcoming_events: list[dict[str, Any]],
    news_issues: list[dict[str, Any]],
    manual_events: list[dict[str, Any]],
    now: datetime | None = None,
    horizon_days: int = 45,
) -> list[dict[str, Any]]:
    current = (now or datetime.now(timezone.utc)).astimezone(KST)
    today = current.date()
    candidates: list[tuple[dict[str, Any], str]] = [(row, "manual") for row in manual_events]
    for row in upcoming_events:
        text = " ".join([_clean(row.get("title")), *map(str, row.get("categories") or [])]).lower()
        if _importance(text, row.get("importance")) != "보통":
            candidates.append((row, "coinmarketcal"))
    for row in news_issues:
        title = _clean(row.get("title"))
        lowered = title.lower()
        if any(term in lowered for term in SCHEDULE_TERMS) and _importance(lowered) != "보통":
            candidates.append((row, "news"))

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row, origin in candidates:
        normalized = _normalize_event(row, today, origin)
        if not normalized:
            continue
        days_until = normalized["days_until"]
        if days_until is not None and (days_until < -3 or days_until > horizon_days):
            continue
        fingerprint = re.sub(r"[^0-9a-z가-힣]", "", normalized["title"].lower())
        if normalized["id"] in seen or fingerprint in seen:
            continue
        seen.update({normalized["id"], fingerprint})
        result.append(normalized)
    result.sort(key=lambda event: (IMPORTANCE_ORDER[event["importance"]], event["date"] or "9999-12-31", event["title"]))
    return result[:12]
