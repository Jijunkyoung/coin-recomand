from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests

from .indicators import annualized_volatility, ema, macd, pct_change, rsi, volume_ratio

KST = timezone(timedelta(hours=9))


class KisDataClient:
    """한국투자증권 시세 전용 클라이언트. 주문 API는 사용하지 않는다."""

    def __init__(self, timeout: int = 20) -> None:
        self.app_key = os.getenv("KIS_APP_KEY", "").strip()
        self.app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        self.base_url = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443").rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self._token: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def _access_token(self) -> str:
        if self._token:
            return self._token
        if not self.configured:
            raise RuntimeError("KIS_APP_KEY와 KIS_APP_SECRET이 등록되지 않았습니다.")
        response = self.session.post(
            f"{self.base_url}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret},
            timeout=self.timeout,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={
                        "content-type": "application/json; charset=utf-8",
                        "authorization": f"Bearer {self._access_token()}",
                        "appkey": self.app_key,
                        "appsecret": self.app_secret,
                        "tr_id": tr_id,
                        "custtype": "P",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                if str(data.get("rt_cd", "0")) != "0":
                    raise RuntimeError(data.get("msg1") or data.get("msg_cd") or "한국투자증권 API 오류")
                return data
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = status in {429, 500, 502, 503, 504} or "EGW00201" in str(exc)
                if not retryable or attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("한국투자증권 API 재시도 실패") from last_error

    @staticmethod
    def _number(value: Any) -> float:
        text = str(value or "0").replace(",", "").strip()
        return float(text or 0)

    def domestic_daily(self, symbol: str, days: int = 120) -> list[dict[str, Any]]:
        end = datetime.now(KST).strftime("%Y%m%d")
        start = (datetime.now(KST) - timedelta(days=max(180, days * 2))).strftime("%Y%m%d")
        items: list[dict[str, Any]] = []
        current_end = end
        for _ in range(3):
            data = self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                "FHKST03010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol, "FID_INPUT_DATE_1": start,
                 "FID_INPUT_DATE_2": current_end, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"},
            )
            page = data.get("output2") or []
            if not page:
                break
            items.extend(page)
            oldest = str(page[-1].get("stck_bsop_date") or "")
            if len(page) < 100 or not oldest or oldest <= start:
                break
            current_end = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            time.sleep(0.15)
        rows, seen = [], set()
        for item in sorted(items, key=lambda row: str(row.get("stck_bsop_date") or "")):
            if not item.get("stck_bsop_date") or self._number(item.get("stck_clpr")) <= 0:
                continue
            if item["stck_bsop_date"] in seen:
                continue
            seen.add(item["stck_bsop_date"])
            rows.append({
                "date": f"{item['stck_bsop_date'][:4]}-{item['stck_bsop_date'][4:6]}-{item['stck_bsop_date'][6:8]}",
                "open": self._number(item.get("stck_oprc")), "high": self._number(item.get("stck_hgpr")),
                "low": self._number(item.get("stck_lwpr")), "price": self._number(item.get("stck_clpr")),
                "volume": self._number(item.get("acml_vol")),
            })
        return rows[-days:]

    def overseas_daily(self, symbol: str, exchange: str, days: int = 120) -> list[dict[str, Any]]:
        data = self._get(
            "/uapi/overseas-price/v1/quotations/dailyprice",
            "HHDFS76240000",
            {"AUTH": "", "EXCD": exchange, "SYMB": symbol, "GUBN": "0", "BYMD": "", "MODP": "1"},
        )
        rows = []
        for item in reversed(data.get("output2") or []):
            raw_date = str(item.get("xymd") or "")
            close = self._number(item.get("clos"))
            if len(raw_date) != 8 or close <= 0:
                continue
            rows.append({
                "date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}",
                "open": self._number(item.get("open")), "high": self._number(item.get("high")),
                "low": self._number(item.get("low")), "price": close, "volume": self._number(item.get("tvol")),
            })
        return rows[-days:]

    def daily(self, market: str, symbol: str, exchange: str, days: int) -> list[dict[str, Any]]:
        return self.domestic_daily(symbol, days) if market == "kr" else self.overseas_daily(symbol, exchange, days)


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def technical_metrics(history: list[dict[str, Any]]) -> dict[str, Any]:
    if len(history) < 50:
        raise ValueError(f"거래이력 부족 ({len(history)}일/최소 50일)")
    closes = [float(row["price"]) for row in history]
    volumes = [float(row.get("volume") or 0) for row in history]
    macd_line, signal, histogram = macd(closes)
    return {
        "price": closes[-1], "ema20": _round(ema(closes, 20)), "ema50": _round(ema(closes, 50)),
        "rsi": _round(rsi(closes)), "macd": _round(macd_line, 4), "macd_signal": _round(signal, 4),
        "macd_histogram": _round(histogram, 4), "return_1d": _round(pct_change(closes, 1)), "return_7d": _round(pct_change(closes, 7)),
        "return_30d": _round(pct_change(closes, 30)), "volume_ratio": _round(volume_ratio(volumes)),
        "volatility": _round(annualized_volatility(closes)), "sparkline": [_round(value, 4) for value in closes[-30:]],
        "history": history,
    }


def stock_score(metrics: dict[str, Any], regime: str) -> tuple[int, list[str], list[str]]:
    score, reasons, risks = 50, [], []
    price, ema20_value, ema50_value = metrics["price"], metrics["ema20"], metrics["ema50"]
    if price > ema20_value > ema50_value:
        score += 18; reasons.append("주가·EMA20·EMA50 정배열(+18)")
    elif price < ema20_value < ema50_value:
        score -= 18; risks.append("주가·EMA20·EMA50 역배열(-18)")
    else:
        reasons.append("EMA 추세 전환 구간(0)")
    rsi_value = metrics.get("rsi")
    if rsi_value is not None and 45 <= rsi_value <= 65:
        score += 8; reasons.append("RSI가 건강한 상승 구간(+8)")
    elif rsi_value is not None and rsi_value >= 75:
        score -= 10; risks.append("RSI 75 이상 과매수(-10)")
    elif rsi_value is not None and rsi_value < 35:
        score -= 4; risks.append("RSI 35 미만 약세(-4)")
    if (metrics.get("macd_histogram") or 0) > 0:
        score += 10; reasons.append("MACD 상승 모멘텀(+10)")
    else:
        score -= 6; risks.append("MACD 모멘텀 약세(-6)")
    ret7, ret30 = metrics.get("return_7d"), metrics.get("return_30d")
    if ret7 is not None and ret30 is not None and 0 < ret7 <= 12 and 3 < ret30 <= 30:
        score += 10; reasons.append("7일·30일 상승세가 과열 없이 지속(+10)")
    elif (ret7 or 0) > 20 or (ret30 or 0) > 45:
        score -= 10; risks.append("단기 급등에 따른 추격매수 위험(-10)")
    volume = metrics.get("volume_ratio")
    if volume is not None and 1.15 <= volume <= 3:
        score += 7; reasons.append("상승 확인 거래량(+7)")
    elif volume is not None and volume > 5:
        score -= 6; risks.append("평균 대비 거래량 급증으로 변동 위험(-6)")
    volatility = metrics.get("volatility")
    if volatility is not None and volatility > 80:
        score -= 8; risks.append("연환산 변동성 80% 초과(-8)")
    elif volatility is not None and 15 <= volatility <= 45:
        score += 3; reasons.append("관리 가능한 변동성 구간(+3)")
    if regime == "상승":
        score += 8; reasons.append("대표지수 상승 국면(+8)")
    elif regime == "하락":
        score -= 8; risks.append("대표지수 하락 국면(-8)")
    return max(0, min(100, round(score))), reasons, risks


def market_regime(benchmark: dict[str, Any]) -> tuple[str, int]:
    points = 50
    if benchmark["price"] > benchmark["ema20"] > benchmark["ema50"]: points += 30
    elif benchmark["price"] < benchmark["ema20"] < benchmark["ema50"]: points -= 30
    points += 10 if (benchmark.get("macd_histogram") or 0) > 0 else -10
    points += 10 if (benchmark.get("return_30d") or 0) > 0 else -10
    points = max(0, min(100, points))
    return ("상승" if points >= 70 else "하락" if points <= 30 else "중립"), points


def parse_sector_selection(value: str, settings: dict[str, Any]) -> list[str]:
    available = settings.get("sectors") or {}
    selected, seen = [], set()
    for raw in re.split(r"[,;\n]+", value or ""):
        sector_id = raw.strip().lower()
        if sector_id and sector_id in available and sector_id not in seen:
            selected.append(sector_id)
            seen.add(sector_id)
    return selected


def parse_holdings(value: str, market_settings: dict[str, Any]) -> list[dict[str, str]]:
    """Parse SYMBOL or SYMBOL|display name without publishing the original Secret."""
    catalog = {
        str(item["symbol"]).upper(): item
        for item in [market_settings.get("benchmark") or {}, *(market_settings.get("universe") or [])]
        if item.get("symbol")
    }
    holdings, seen = [], set()
    for raw in re.split(r"[,;\n]+", value or ""):
        parts = [part.strip() for part in raw.split("|", 1)]
        symbol = parts[0].upper() if parts else ""
        if not symbol or symbol in seen or not re.fullmatch(r"[A-Z0-9.\-]{1,12}", symbol):
            continue
        known = catalog.get(symbol) or {}
        name = parts[1] if len(parts) > 1 and parts[1] else str(known.get("name") or symbol)
        holdings.append({"symbol": symbol, "name": name})
        seen.add(symbol)
    return holdings


def selected_universe(market: str, settings: dict[str, Any], sector_ids: list[str]) -> list[dict[str, Any]]:
    symbols: set[str] = set()
    for sector_id in sector_ids:
        symbols.update(str(symbol).upper() for symbol in settings["sectors"][sector_id].get(market, []))
    return [item for item in settings[market].get("universe", []) if str(item.get("symbol", "")).upper() in symbols]


def collect_stock_news(
    holdings: dict[str, list[dict[str, str]]],
    sector_ids: list[str],
    settings: dict[str, Any],
    limit: int = 14,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    holding_items = [item for market in ("us", "kr") for item in holdings.get(market, [])]
    sector_items = [(sector_id, settings["sectors"][sector_id]) for sector_id in sector_ids]
    terms: list[str] = []
    for item in holding_items:
        terms.extend([item["name"], item["symbol"]])
    for _, sector in sector_items:
        terms.extend(sector.get("news_terms") or [sector.get("label", "")])
    terms = list(dict.fromkeys(term.strip() for term in terms if term and term.strip()))[:24]
    if not terms:
        return []
    query = "(" + " OR ".join(f'\"{term}\"' for term in terms) + ") (주식 OR 증시 OR 실적 OR 수주 OR 투자) when:1d"
    response = (session or requests.Session()).get(
        "https://news.google.com/rss/search",
        params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
        headers={"User-Agent": "Mozilla/5.0 coin-recomand/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    root, now, seen, issues = ET.fromstring(response.text), datetime.now(timezone.utc), set(), []
    positive_words = ("수주", "계약", "호실적", "상향", "증가", "성장", "승인", "투자", "신고가")
    negative_words = ("급락", "하락", "적자", "감소", "소송", "제재", "리콜", "해킹", "중단")
    for node in root.findall(".//item"):
        raw_title = " ".join((node.findtext("title") or "").split())
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = " ".join(((source_node.text if source_node is not None else "") or "").split()) or "Google News"
        title = re.sub(rf"\s+-\s+{re.escape(source)}\s*$", "", raw_title, flags=re.IGNORECASE).strip()
        if not title or not link:
            continue
        normalized = re.sub(r"[^0-9a-z가-힣]", "", title.lower())
        fingerprint = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
        if not normalized or fingerprint in seen:
            continue
        try:
            published = parsedate_to_datetime(node.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            published = now
        if published < now - timedelta(hours=36):
            continue
        lower = title.lower()
        related_holdings = [item["symbol"] for item in holding_items if item["name"].lower() in lower or re.search(rf"(?<![A-Z0-9]){re.escape(item['symbol'])}(?![A-Z0-9])", title, re.IGNORECASE)]
        related_sectors = [sector["label"] for _, sector in sector_items if any(str(term).lower() in lower for term in sector.get("news_terms") or [])]
        if not related_holdings and not related_sectors:
            continue
        positive = sum(word in lower for word in positive_words)
        negative = sum(word in lower for word in negative_words)
        impact = "악재 가능" if negative > positive else "호재 가능" if positive > negative else "중립·혼재"
        seen.add(fingerprint)
        issues.append({
            "title": title, "url": link, "source": source, "impact": impact,
            "published_at": published.isoformat(), "published_at_kst": published.astimezone(KST).strftime("%m-%d %H:%M"),
            "related_holdings": related_holdings, "related_sectors": related_sectors,
        })
        if len(issues) >= limit:
            break
    return issues


def build_stock_report(
    market: str,
    settings: dict[str, Any],
    client: KisDataClient | None = None,
    universe: list[dict[str, Any]] | None = None,
    selected_sectors: list[str] | None = None,
) -> dict[str, Any]:
    if market not in {"us", "kr"}:
        raise ValueError("market은 us 또는 kr이어야 합니다.")
    client = client or KisDataClient()
    now = datetime.now(timezone.utc)
    market_settings = settings[market]
    selection_mode = universe is not None
    selected_sectors = selected_sectors if selected_sectors is not None else []
    sector_options = [{"id": key, "label": value["label"]} for key, value in (settings.get("sectors") or {}).items()]
    base = {
        "schema_version": 1, "market": market, "market_name": "미국주식" if market == "us" else "국내주식",
        "currency": "USD" if market == "us" else "KRW", "generated_at": now.isoformat(),
        "generated_at_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"), "configured": client.configured,
        "recommendations": [], "rankings": [], "warnings": [], "sector_options": sector_options,
        "selected_sectors": selected_sectors,
    }
    if not client.configured:
        base.update({"status": "설정 필요", "regime": "미수집", "market_score": None,
                     "warnings": ["KIS_APP_KEY·KIS_APP_SECRET을 GitHub Secret에 등록하면 분석이 시작됩니다."]})
        return base
    days = int(settings.get("history_days", 120))
    try:
        benchmark_info = market_settings["benchmark"]
        benchmark_history = client.daily(market, benchmark_info["symbol"], benchmark_info["exchange"], days)
        benchmark = {**benchmark_info, **technical_metrics(benchmark_history)}
        regime, regime_score = market_regime(benchmark)
    except Exception as exc:
        base.update({"status": "오류", "regime": "미수집", "market_score": None,
                     "warnings": [f"대표지수 분석 실패: {type(exc).__name__} · {exc}"]})
        return base
    rankings = []
    analysis_universe = market_settings["universe"] if universe is None else universe
    for item in analysis_universe:
        try:
            history = client.daily(market, item["symbol"], item["exchange"], days)
            metrics = technical_metrics(history)
            score, reasons, risks = stock_score(metrics, regime)
            decision = "분할매수 후보" if score >= (82 if regime == "상승" else 90) else "관찰" if score >= 65 else "보류"
            if regime == "하락" and decision == "분할매수 후보": decision = "관찰"
            rankings.append({**item, **metrics, "score": score, "decision": decision, "reasons": reasons, "risks": risks})
        except Exception as exc:
            base["warnings"].append(f"{item['name']}({item['symbol']}) 분석 제외: {type(exc).__name__} · {exc}")
        time.sleep(0.12)
    rankings.sort(key=lambda row: row["score"], reverse=True)
    for index, row in enumerate(rankings, 1): row["rank"] = index
    status = "선택 필요" if selection_mode and not analysis_universe else "정상" if rankings else "오류"
    if status == "선택 필요":
        base["warnings"].append("분석할 섹터를 선택한 뒤 STOCK_SECTORS Secret에 저장해 주세요.")
    base.update({
        "status": status, "regime": regime, "market_score": regime_score,
        "benchmark": benchmark, "rankings": rankings,
        "recommendations": rankings[: int(settings.get("recommendation_count", 5))], "screened": len(rankings),
        "methodology": {
            "intro": "주식은 50점에서 시작해 기술 추세·거래량·변동성·대표지수 국면을 가감합니다. 재무·공시 데이터는 다음 확장 단계에서 별도 점수로 표시하며 현재 점수에 추정값을 넣지 않습니다.",
            "items": ["EMA 정배열 +18 / 역배열 -18", "RSI 45~65 +8 / 75 이상 -10 / 35 미만 -4",
                      "MACD 히스토그램 양수 +10 / 그 외 -6", "과열 없는 7·30일 상승 +10 / 급등 -10",
                      "거래량 확인 +7 / 비정상 급증 -6", "변동성 적정 +3 / 80% 초과 -8", "대표지수 상승 +8 / 하락 -8"],
            "decisions": "상승장 82점, 중립장 90점 이상 분할매수 후보. 65점 이상 관찰. 하락장에서는 신규 매수 후보를 내지 않습니다.",
        },
        "sources": [{"name": "한국투자증권 Open API", "url": "https://apiportal.koreainvestment.com/"}],
        "disclaimer": "정량 지표 기반 연구용 정보이며 투자 자문이나 수익 보장이 아닙니다. 실제 주문은 실행하지 않습니다.",
    })
    return base


def load_settings(path: str | Path = "config/stocks.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def generate_stock_reports(settings_path: str | Path = "config/stocks.json", output_dir: str | Path = "docs/data") -> dict[str, dict[str, Any]]:
    settings, output = load_settings(settings_path), Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    client = KisDataClient()
    sector_ids = parse_sector_selection(os.getenv("MEMBER_STOCK_SECTORS") or os.getenv("STOCK_SECTORS", ""), settings)
    holdings = {
        "us": parse_holdings(os.getenv("MEMBER_STOCK_HOLDINGS_US") or os.getenv("STOCK_HOLDINGS_US", ""), settings["us"]),
        "kr": parse_holdings(os.getenv("MEMBER_STOCK_HOLDINGS_KR") or os.getenv("STOCK_HOLDINGS_KR", ""), settings["kr"]),
    }
    reports = {
        market: build_stock_report(market, settings, client, selected_universe(market, settings, sector_ids), sector_ids)
        for market in ("us", "kr")
    }
    try:
        news_issues = collect_stock_news(holdings, sector_ids, settings)
    except Exception as exc:
        news_issues = []
        for report in reports.values():
            report["warnings"].append(f"맞춤 주식뉴스 미수집: {type(exc).__name__}")
    for market, report in reports.items():
        (output / f"stocks-{market}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{report['market_name']} 분석 저장: {len(report['rankings'])}개")
    portfolio = None
    portfolio_path = os.getenv("MEMBER_KIS_PORTFOLIO_PATH", "").strip()
    if portfolio_path:
        try:
            portfolio = json.loads(Path(portfolio_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            for report in reports.values():
                report["warnings"].append(f"회원 KIS 계좌변동 미수집: {type(exc).__name__}")
    reports["_mail"] = {
        "news_issues": news_issues,
        "holding_counts": {market: len(items) for market, items in holdings.items()},
        "selected_sector_labels": [settings["sectors"][sector_id]["label"] for sector_id in sector_ids],
        "portfolio": portfolio,
    }
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="미국·국내주식 분석 생성")
    parser.add_argument("--settings", default="config/stocks.json")
    parser.add_argument("--output-dir", default="docs/data")
    args = parser.parse_args()
    generate_stock_reports(args.settings, args.output_dir)


if __name__ == "__main__":
    main()
