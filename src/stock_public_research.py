"""Bounded, public-only economic/calendar/company collectors, independent of mail."""
from __future__ import annotations

import calendar
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests

from .stock_sentiment import KST, indicator, number, parse_csv, parse_fred_page

HEADERS = {"User-Agent": "coin-recomand/1.0 (https://github.com/Jijunkyoung/coin-recomand)",
           "Accept": "application/json,text/calendar,application/atom+xml,text/html"}
BLS = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA = "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"
FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
EARNINGS = "https://www.nasdaq.com/market-activity/earnings"
IPO = "https://www.nasdaq.com/market-activity/ipos"
DART = "https://dart.fss.or.kr/api/todayRSS.xml"
ET_ZONE = ZoneInfo("America/New_York")


def download(url: str, json: bool = False):
    response = requests.get(url, headers=HEADERS, timeout=12)
    response.raise_for_status()
    if not json:
        response.encoding = "utf-8"
        return response.text
    payload = response.json()
    if isinstance(payload, dict) and (payload.get("status") or {}).get("rCode", 200) != 200:
        raise ValueError("Provider reported an error")
    return payload


def title_info(title: str) -> tuple[str, str]:
    terms = (("consumer price index", "미국 소비자물가지수(CPI)"),
             ("employment situation", "미국 고용보고서"),
             ("producer price index", "미국 생산자물가지수(PPI)"),
             ("gross domestic product", "미국 국내총생산(GDP)"),
             ("personal income and outlays", "미국 개인소득·지출(PCE 포함)"),
             ("job openings and labor turnover", "미국 구인·이직 보고서(JOLTS)"))
    for text, korean in terms:
        if text in title.lower():
            return korean, "높음" if text != "job openings and labor turnover" else "보통"
    return title, "보통"


def parse_ics(text: str, source: str, source_url: str, now: datetime) -> list[dict]:
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    if "BEGIN:VCALENDAR" not in unfolded and "BEGIN:VEVENT" not in unfolded:
        raise ValueError("Not an iCalendar response")
    result, revisions = {}, {}
    for block in re.findall(r"BEGIN:VEVENT\s*(.*?)END:VEVENT", unfolded, re.S):
        props = {}
        for line in block.splitlines():
            key, colon, value = line.partition(":")
            if colon:
                props[key] = value.strip()
        uid = props.get("UID", "")
        sequence = int(props.get("SEQUENCE", "0")) if props.get("SEQUENCE", "0").isdigit() else 0
        if uid and sequence < revisions.get(uid, -1):
            continue
        if uid:
            revisions[uid] = sequence
            result.pop(uid, None)
        if props.get("STATUS") == "CANCELLED":
            continue
        start = next(((key, value) for key, value in props.items() if key.split(";")[0] == "DTSTART"), None)
        title = props.get("SUMMARY", "").replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")
        if not start or not title:
            continue
        key, value = start
        try:
            if len(value) == 8:
                day, stamp = datetime.strptime(value, "%Y%m%d").date(), None
            else:
                stamp = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
                if value.endswith("Z"):
                    stamp = stamp.replace(tzinfo=timezone.utc)
                elif "TZID=" in key:
                    zone = re.search(r"TZID=([^;]+)", key)[1].strip('"')
                    if zone == "US-Eastern": zone = "America/New_York"
                    stamp = stamp.replace(tzinfo=ZoneInfo(zone))
                else:
                    continue  # No guessed timezone for floating local times.
                day = stamp.astimezone(KST).date()
        except (ValueError, KeyError):
            continue
        if not now.astimezone(KST).date() - timedelta(days=7) <= day <= now.astimezone(KST).date() + timedelta(days=45):
            continue
        translated, importance = title_info(title)
        uid = props.get("UID", f"{value}:{title}")
        row = {"id": source + ":" + uid, "date": day.isoformat(), "at": stamp.astimezone(timezone.utc).isoformat() if stamp else None,
               "title": translated, "original_title": title, "importance": importance, "source": source, "source_url": source_url,
               "sequence": sequence}
        if uid not in result or sequence >= result[uid]["sequence"]:
            result[uid] = row
    return sorted(result.values(), key=lambda row: row["at"] or row["date"])


def parse_fomc(text: str, now: datetime) -> list[dict]:
    headings = list(re.finditer(r"(\d{4}) FOMC Meetings\s*</a>\s*</h4>", text))
    rows = []
    for index, heading in enumerate(headings):
        year = int(heading[1])
        block = text[heading.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        pairs = re.findall(r'class="[^"]*fomc-meeting__month[^"\n]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*fomc-meeting__date[^"\n]*"[^>]*>(.*?)</div>', block, re.S)
        for raw_month, raw_days in pairs:
            month_text = re.sub(r"<[^>]+>", "", raw_month).strip().split("/")[-1].strip()
            months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
            months.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
            month = months.get(month_text.lower())
            days = re.findall(r"\d{1,2}", re.sub(r"<[^>]+>", "", raw_days))
            if not month or not days:
                continue
            try:
                day = date(year, month, int(days[-1]))
            except ValueError:
                continue
            if now.astimezone(ET_ZONE).date() - timedelta(days=7) <= day <= now.astimezone(ET_ZONE).date() + timedelta(days=45):
                rows.append({"id": f"fomc:{day}", "date": day.isoformat(), "at": None, "title": "FOMC 정례회의 마지막 날",
                             "original_title": "Meeting date · announcement time not specified by this calendar",
                             "importance": "높음", "source": "Federal Reserve", "source_url": FOMC})
    if not headings:
        raise ValueError("FOMC calendar structure unavailable")
    return rows


def fred_series(series: str, now: datetime) -> list[dict]:
    try:
        rows = parse_csv(download(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={(now-timedelta(days=100)):%Y-%m-%d}"), series, now)
        if rows: return rows
    except (requests.RequestException, ValueError):
        pass
    return parse_fred_page(download(f"https://fred.stlouisfed.org/series/{series}"), now)


def collect_macro(reports: dict, now: datetime) -> list[dict]:
    definitions = [("DGS2", "미 국채 2년 금리", "%", "일별 고시 금리 · 실시간 아님"),
                   ("DFF", "미 연방기금 실효금리", "%", "실제 거래 기반 실효금리이며 FOMC 목표금리 상단과 다릅니다."),
                   ("DCOILWTICO", "WTI 현물유 가격", "USD/배럴", "EIA 현물 관측값 · WTI 선물 가격이 아닙니다."),
                   ("DTWEXBGS", "미 광의 무역가중 달러지수", "지수", "연준 광의 지수이며 ICE DXY와 다릅니다. 공표 시차가 있습니다.")]
    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [(definition, pool.submit(fred_series, definition[0], now)) for definition in definitions]
        for (series, label, unit, note), future in pending:
            try: observations = future.result()
            except (requests.RequestException, ValueError): observations = []
            rows.append(indicator(series, label, observations, unit, "연준·FRED", f"https://fred.stlouisfed.org/series/{series}", note, now, max_age=10))
    ten = next((row for row in reports.get("us", {}).get("market_context", {}).get("indicators", []) if row["id"] == "us10y"), None)
    if ten is None:
        try: observations = fred_series("DGS10", now)
        except (requests.RequestException, ValueError): observations = []
        ten = indicator("us10y", "미 국채 10년 금리", observations, "%", "연준·FRED", "https://fred.stlouisfed.org/series/DGS10", "일별 고시 금리 · 실시간 아님", now)
    rows.insert(1, ten)
    two = next(row for row in rows if row["id"] == "DGS2")
    spread = [{"date": two["date"], "value": ten["value"] - two["value"]}] if ten and ten.get("date") == two.get("date") and number(ten.get("value")) is not None and number(two.get("value")) is not None else []
    rows.insert(2, indicator("yield_spread", "미 10년−2년 금리차", spread, "%p", "연준·FRED", "https://fred.stlouisfed.org/series/DGS10", "동일 관측일의 두 금리만 차감합니다. 관측일이 다르면 미수집으로 표시합니다.", now))
    return rows


def amount(value):
    if value is None: return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"): text = "-" + text[1:-1]
    return number(text)


def parse_earnings(payload: dict, day: date) -> list[dict]:
    data = payload.get("data") or {}
    if data.get("rows") and not data.get("asOf"):
        raise ValueError("Missing earnings observation date")
    if data.get("asOf"):
        # Never attach the requested day to a cached response for another day.
        try:
            if datetime.strptime(data["asOf"], "%a, %b %d, %Y").date() != day:
                raise ValueError("Earnings response date mismatch")
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid earnings observation date") from exc
    result = []
    for row in data.get("rows") or []:
        symbol = str(row.get("symbol") or "")
        if not re.fullmatch(r"[A-Z0-9.\-]{1,12}", symbol): continue
        result.append({"date": day.isoformat(), "symbol": symbol, "name": row.get("name") or symbol,
                       "session": {"time-pre-market": "장전", "time-after-hours": "장후"}.get(row.get("time"), "시간대 미제공"),
                       "eps_estimate": amount(row.get("epsForecast")), "last_year_eps": amount(row.get("lastYearEPS")),
                       "estimates_count": amount(row.get("noOfEsts")), "market_cap": amount(row.get("marketCap")),
                       "source_url": EARNINGS + "?date=" + day.isoformat()})
    return result


def collect_earnings(now: datetime) -> tuple[list[dict], list[str]]:
    today = now.astimezone(ET_ZONE).date()
    days = [today + timedelta(days=offset) for offset in range(-1, 8)]
    def fetch(day):
        return parse_earnings(download("https://api.nasdaq.com/api/calendar/earnings?date=" + day.isoformat(), json=True), day)
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [(day, pool.submit(fetch, day)) for day in days]
        for day, future in pending:
            try: rows.extend(future.result())
            except (requests.RequestException, ValueError): errors.append(str(day))
    return sorted(rows, key=lambda row: (row["date"], -(row["market_cap"] or 0), row["symbol"])), errors


def parse_filings(payload: dict, stock: dict, now: datetime) -> list[dict]:
    recent, output = payload.get("filings", {}).get("recent", {}), []
    cik = str(payload.get("cik") or "")
    if not cik.isdigit(): return []
    def field(name, i):
        values = recent.get(name, [])
        return values[i] if i < len(values) else ""
    for i, form in enumerate(recent.get("form", [])):
        if form not in {"8-K", "10-Q", "10-K", "6-K", "20-F"}: continue
        filed = field("filingDate", i)
        try: day = date.fromisoformat(filed)
        except ValueError: continue
        if not now.astimezone(ET_ZONE).date() - timedelta(days=90) <= day <= now.astimezone(ET_ZONE).date(): continue
        accession, document = field("accessionNumber", i), field("primaryDocument", i)
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) or not re.fullmatch(r"[A-Za-z0-9_.\-]+", document) or ".." in document: continue
        output.append({"market": "us", "symbol": stock["symbol"], "name": stock["name"], "date": filed,
                       "form": form, "report_date": field("reportDate", i),
                       "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{quote(document)}"})
        if len(output) == 8: break
    return output


def collect_filings(settings: dict, now: datetime) -> tuple[list[dict], list[str]]:
    tickers = download("https://www.sec.gov/files/company_tickers.json", json=True)
    mapping = {row["ticker"]: row["cik_str"] for row in tickers.values()}
    def fetch(stock):
        time.sleep(.2)  # Two workers, below SEC's public request-rate limit.
        cik = mapping.get(stock["symbol"])
        if cik is None: raise ValueError("Ticker not found")
        payload = download(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", json=True)
        return parse_filings(payload, stock, now)
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [(stock["symbol"], pool.submit(fetch, stock)) for stock in settings["us"].get("universe", [])]
        for symbol, future in pending:
            try: rows.extend(future.result())
            except (requests.RequestException, ValueError): errors.append(symbol)
    return sorted(rows, key=lambda row: (row["date"], row["symbol"]), reverse=True), errors


def parse_dart(text: str, settings: dict, now: datetime) -> list[dict]:
    rows = []
    root = ET.fromstring(text)
    if root.tag != "rss": raise ValueError("Not a DART RSS response")
    for item in root.findall(".//item"):
        title = unescape(item.findtext("title") or "")
        url = item.findtext("link") or ""
        if not re.fullmatch(r"https?://dart\.fss\.or\.kr/(?:api/link\.jsp|dsaf001/main\.do)\?rcpNo=\d+", url): continue
        # Match the publisher, not another company mentioned in the title.
        creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator") or ""
        company = re.sub(r"\s+", "", creator)
        stock = next((x for x in settings["kr"].get("universe", []) if re.sub(r"\s+", "", x["name"]) == company), None)
        if not stock: continue
        try:
            published = item.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
            stamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if stamp.tzinfo is None: continue
            day = stamp.astimezone(KST).date()
        except ValueError: continue
        if day != now.astimezone(KST).date(): continue
        rows.append({"market": "kr", "symbol": stock["symbol"], "name": stock["name"], "date": str(day),
                     "form": title.split(" - ", 1)[-1], "report_date": "", "url": url.replace("http://", "https://", 1)})
    return rows


def parse_ipos(payload: dict) -> list[dict]:
    output = []
    groups = (("upcoming", "공모 예정 · 추정", "expectedPriceDate", "예정일 · 추정"),
              ("priced", "공모가 확정", "pricedDate", "공모가 확정일"),
              ("filed", "등록신고", "filedDate", "신고일"),
              ("withdrawn", "철회", "withdrawDate", "철회일"))
    for group, status, date_field, date_kind in groups:
        for row in ((payload.get("data") or {}).get(group) or {}).get("rows") or []:
            value = row.get(date_field)
            try: day = datetime.strptime(str(value), "%m/%d/%Y").date().isoformat()
            except ValueError: day = None
            output.append({"name": row.get("companyName") or "기업명 미제공", "symbol": row.get("proposedTickerSymbol"),
                           "date": day, "date_kind": date_kind, "status": status,
                           "price": row.get("proposedSharePrice"), "amount": row.get("dollarValueOfSharesOffered"),
                           "exchange": row.get("proposedExchange"), "source_url": IPO,
                           "id": f"{group}:{row.get('dealID') or row.get('companyName')}"})
    return output


def collect_ipos(now: datetime) -> tuple[list[dict], list[str]]:
    today = now.astimezone(ET_ZONE).date()
    base = today.year * 12 + today.month - 1
    rows, errors = {}, []
    for offset in (-1, 0, 1):
        year, month = divmod(base + offset, 12)
        query = f"{year}-{month + 1:02d}"
        try:
            payload = download("https://api.nasdaq.com/api/ipo/calendar?date=" + query, json=True)
            period = payload.get("data") or {}
            if period.get("year") is not None and period.get("month") is not None and (int(period["year"]), int(period["month"])) != (year, month + 1):
                raise ValueError("IPO response month mismatch")
            for row in parse_ipos(payload): rows[row["id"]] = row
        except (requests.RequestException, ValueError): errors.append(query)
    return sorted(rows.values(), key=lambda row: row["date"] or "", reverse=True), errors


def collect_public_research(reports: dict, settings: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    result = {"schema_version": 1, "generated_at": now.isoformat(), "economic_events": [], "macro_indicators": [],
              "earnings": [], "filings": [], "ipos": [], "sources": {},
              "options": {"status": "보류", "reason": "무료로 지속 사용 가능한 옵션 원자료·권한 미확보. 유료 구독은 추가하지 않았습니다."}}
    tasks = {
        "bls": ("BLS 발표 일정", BLS, "economic_events", lambda: parse_ics(download(BLS), "BLS", "https://www.bls.gov/schedule/", now)),
        "bea": ("BEA 발표 일정", BEA, "economic_events", lambda: parse_ics(download(BEA), "BEA", "https://www.bea.gov/news/schedule", now)),
        "fomc": ("연준 회의일", FOMC, "economic_events", lambda: parse_fomc(download(FOMC), now)),
        "macro": ("금리·원유·달러 참고지표", "https://fred.stlouisfed.org/", "macro_indicators", lambda: collect_macro(reports, now)),
        "earnings": ("Nasdaq 미국 실적일정", EARNINGS, "earnings", lambda: collect_earnings(now)),
        "sec": ("SEC 분석종목 공시", "https://www.sec.gov/search-filings", "filings", lambda: collect_filings(settings, now)),
        "dart": ("DART 최근 RSS 중 당일·분석종목 공시", "https://dart.fss.or.kr/", "filings", lambda: parse_dart(download(DART), settings, now)),
        "ipo": ("Nasdaq 공모정보", IPO, "ipos", lambda: collect_ipos(now)),
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [(key, pool.submit(task[3])) for key, task in tasks.items()]
        for key, future in pending:
            label, url, target, _ = tasks[key]
            status, count = "정상 수집", 0
            try:
                collected = future.result()
                if isinstance(collected, tuple):
                    collected, errors = collected
                    if errors: status = f"일부 미수집: {', '.join(errors)}"
                count = len(collected)
                result[target].extend(collected)
                if key == "macro" and any(row.get("value") is None for row in collected): status = "일부 지표 미수집"
            except (requests.RequestException, ValueError, KeyError, TypeError, ET.ParseError) as error:
                code = getattr(getattr(error, "response", None), "status_code", None)
                status = f"미수집 · HTTP {code}" if code else "미수집 · 자료 형식 또는 연결 확인 필요"
            result["sources"][key] = {"label": label, "url": url, "status": status, "count": count, "observed_at": now.isoformat()}
    result["economic_events"].sort(key=lambda row: row["at"] or row["date"])
    result["filings"].sort(key=lambda row: (row["date"], row["symbol"]), reverse=True)
    return result
