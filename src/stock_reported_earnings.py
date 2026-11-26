"""Reported entity-wide SEC XBRL facts; never mix consensus and GAAP EPS."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests

from .stock_sentiment import number

CONCEPTS = {
    "us-gaap": {"eps": ["EarningsPerShareDiluted"], "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]},
    "ifrs-full": {"eps": ["DilutedEarningsLossPerShare"], "revenue": ["Revenue"]},
}


def observations(payload: dict, taxonomy: str, metric: str, now: datetime) -> list[dict]:
    today = now.date()
    facts = payload.get("facts", {}).get(taxonomy, {})
    unit = "USD/shares" if metric == "eps" else "USD"
    rows = []
    for priority, tag in enumerate(CONCEPTS[taxonomy][metric]):
        for item in facts.get(tag, {}).get("units", {}).get(unit, []):
            try:
                start, end, filed = (date.fromisoformat(str(item[key])) for key in ("start", "end", "filed"))
            except (KeyError, ValueError): continue
            days = (end - start).days + 1
            kind = "quarter" if 61 <= days <= 121 else "annual" if 335 <= days <= 395 else None
            value, accession = number(item.get("val")), str(item.get("accn", ""))
            if not kind or value is None or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession): continue
            if filed > today or end > today or end < today - timedelta(days=900) or filed < end: continue
            if item.get("form") not in {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "6-K"}: continue
            rows.append({"start": str(start), "end": str(end), "filed": str(filed), "days": days,
                         "kind": kind, "value": value, "accn": accession, "form": item["form"],
                         "tag": tag, "unit": unit, "priority": priority})
    return rows


def pick(rows: list[dict], start: str, end: str) -> dict | None:
    choices = [row for row in rows if row["start"] == start and row["end"] == end]
    # Stable concept priority, then latest filing/restatement as of collection.
    return sorted(choices, key=lambda row: (row["priority"], -date.fromisoformat(row["filed"]).toordinal(), row["accn"]), reverse=False)[0] if choices else None


def comparable(rows: list[dict], current: dict | None) -> dict | None:
    if current is None: return None
    end = date.fromisoformat(current["end"])
    candidates = [row for row in rows if row["tag"] == current["tag"] and row["unit"] == current["unit"]
                  and row["kind"] == current["kind"] and row["accn"] == current["accn"]
                  and 345 <= (end-date.fromisoformat(row["end"])).days <= 385
                  and abs(row["days"]-current["days"]) <= 14]
    return min(candidates, key=lambda row: abs((end-date.fromisoformat(row["end"])).days-365)) if candidates else None


def eps_comparison(current: float | None, prior: float | None) -> tuple[float | None, str]:
    if current is None or prior is None: return None, "동일 공시 전년 비교값 미수집"
    if prior < 0:
        return None, "흑자전환" if current > 0 else "손익분기" if current == 0 else "적자축소" if current > prior else "적자확대" if current < prior else "적자유지"
    if prior == 0: return None, "전년 EPS 0 · 증감률 미산출"
    if current < 0: return None, "적자전환"
    return (current/prior-1)*100, "손익분기" if current == 0 else "증가" if current > prior else "감소" if current < prior else "동일"


def parse_reported_earnings(payload: dict, stock: dict, now: datetime, cik: int | None = None) -> list[dict]:
    identity = str(payload.get("cik", ""))
    if not identity.isdigit() or (cik is not None and int(identity) != cik): raise ValueError("SEC CIK identity mismatch")
    by_taxonomy = {taxonomy: {key: observations(payload, taxonomy, key, now) for key in ("eps", "revenue")} for taxonomy in CONCEPTS}
    valid = [(max(row["end"] for rows in values.values() for row in rows), taxonomy) for taxonomy, values in by_taxonomy.items() if any(values.values())]
    if not valid: return []
    latest = max(item[0] for item in valid)
    taxonomy = next(key for key in CONCEPTS if (latest, key) in valid)
    metrics = by_taxonomy[taxonomy]
    result = []
    for kind in ("quarter", "annual"):
        anchors = [row for rows in metrics.values() for row in rows if row["kind"] == kind and row["end"] >= str(now.date()-timedelta(days=500))]
        if not anchors: continue
        end = max(row["end"] for row in anchors)
        anchor = next((row for row in metrics["eps"] if row["kind"] == kind and row["end"] == end), next(row for row in anchors if row["end"] == end))
        start = anchor["start"]
        selected = {key: pick(rows, start, end) for key, rows in metrics.items()}
        prior = {key: comparable(metrics[key], selected[key]) for key in metrics}
        def value(rows, key): return rows[key]["value"] if rows[key] else None
        eps, revenue, previous_eps, previous_revenue = value(selected,"eps"), value(selected,"revenue"), value(prior,"eps"), value(prior,"revenue")
        eps_yoy, eps_state = eps_comparison(eps, previous_eps)
        source = selected["eps"] or selected["revenue"]
        def filing_url(item):
            return f"https://www.sec.gov/Archives/edgar/data/{int(identity)}/{item['accn'].replace('-', '')}/{item['accn']}-index.html" if item else None
        result.append({"market": "us", "symbol": stock["symbol"], "name": stock["name"], "date": end,
                       "period_start": start, "period_end": end, "period_type": kind, "basis": "US-GAAP" if taxonomy == "us-gaap" else "IFRS",
                       "eps": eps, "revenue": revenue, "currency": "USD", "previous_eps": previous_eps, "previous_revenue": previous_revenue,
                       "eps_yoy": eps_yoy, "eps_state": eps_state,
                       "revenue_yoy": (revenue/previous_revenue-1)*100 if revenue is not None and previous_revenue is not None and previous_revenue > 0 else None,
                       "eps_filed": selected["eps"]["filed"] if selected["eps"] else None,
                       "revenue_filed": selected["revenue"]["filed"] if selected["revenue"] else None,
                       "eps_tag": selected["eps"]["tag"] if selected["eps"] else None, "revenue_tag": selected["revenue"]["tag"] if selected["revenue"] else None,
                       "eps_source_url": filing_url(selected["eps"]), "revenue_source_url": filing_url(selected["revenue"]),
                       "form": source["form"], "filed": source["filed"], "accession": source["accn"],
                       "source_url": filing_url(source)})
    return sorted(result, key=lambda row: row["date"], reverse=True)


def collect_reported_earnings(settings: dict, now: datetime) -> tuple[list[dict], list[str]]:
    from .stock_public_research import download, failure_label, sec_identifiers
    mapping = sec_identifiers(settings)
    def fetch(stock):
        time.sleep(.25)
        cik = mapping.get(stock["symbol"])
        if cik is None: raise ValueError("SEC CIK identity mismatch")
        payload = download(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", json=True)
        return parse_reported_earnings(payload, stock, now, int(cik))
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [(stock["symbol"], pool.submit(fetch, stock)) for stock in settings.get("us", {}).get("universe", [])]
        for symbol, future in pending:
            try:
                result = future.result()
                if not result: errors.append(symbol + " (기간·통화 기준 일치 자료 없음)")
                rows.extend(result)
            except (requests.RequestException, ValueError) as error: errors.append(f"{symbol} ({failure_label(error)})")
    return sorted(rows, key=lambda row: (row["date"], row["symbol"]), reverse=True), errors
