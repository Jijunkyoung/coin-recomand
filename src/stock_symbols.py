"""Public listing directory, separate from the small scheduled analysis universe.

Formats: Korea Investment's open-trading-api/stocks_info examples. TLS remains
verified; archives are read in memory, never extracted to arbitrary paths.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
from zipfile import ZipFile

BASE = "https://new.real.download.dws.co.kr/common/master/"
PUBLIC_BASE = "https://jijunkyoung.github.io/coin-recomand/data/"
SOURCES = {
    "NAS": ("us", "nasmst.cod", "NASDAQ"),
    "NYS": ("us", "nysmst.cod", "NYSE"),
    "AMS": ("us", "amsmst.cod", "NYSE American"),
    "KOSPI": ("kr", "kospi_code.mst", "코스피"),
    "KOSDAQ": ("kr", "kosdaq_code.mst", "코스닥"),
    "KONEX": ("kr", "konex_code.mst", "코넥스"),
}
KINDS = {"ST": "주식", "FS": "외국주식", "DR": "예탁증서", "RT": "리츠",
         "EF": "ETF", "EN": "ETN", "IF": "인프라펀드", "MF": "상장펀드", "PF": "상장펀드"}


def parse_master(raw: bytes, exchange: str) -> list[dict]:
    market, _, label = SOURCES[exchange]
    result = {}
    for line in raw.splitlines():
        if market == "us":
            fields = line.decode("cp949").split("\t")
            if len(fields) < 10 or fields[0] != "US" or fields[2] != exchange:
                continue
            symbol, name, english, kind = (fields[i].strip() for i in (4, 6, 7, 8))
            if kind not in {"2", "3"} or not re.fullmatch(r"[A-Z0-9][A-Z0-9./\-]{0,15}", symbol):
                continue
            kind = "ETF·ETP" if kind == "3" else "주식·우선주"
        else:
            if len(line) < 63:
                continue
            # All three masters have a 9-byte code, 12-byte ISIN, 40-byte name.
            # Slice bytes before decoding: Korean characters have variable width.
            symbol = line[:9].decode("cp949").strip()
            name = line[21:61].decode("cp949").strip()
            group = line[61:63].decode("ascii")
            if group not in KINDS or not re.fullmatch(r"(?:[A-Z0-9]{6}|Q[0-9]{6})", symbol):
                continue
            kind, english = KINDS[group], ""
        if not name:
            continue
        result[symbol] = {"symbol": symbol, "name": name, "english_name": english,
                          "exchange": exchange, "exchange_name": label, "kind": kind}
    return sorted(result.values(), key=lambda row: row["symbol"])


def download(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "coin-recomand-symbol-directory/1.0"}), timeout=18) as response:
        data = response.read(12_000_001)
    if len(data) > 12_000_000:
        raise ValueError("종목목록 크기 초과")
    return data


def fetch_master(exchange: str) -> list[dict]:
    filename = SOURCES[exchange][1]
    with ZipFile(BytesIO(download(BASE + filename + ".zip"))) as archive:
        members = [item for item in archive.infolist() if item.filename.lower() == filename.lower()]
        if len(members) != 1 or members[0].file_size > 12_000_000:
            raise ValueError("종목마스터 압축 형식 오류")
        rows = parse_master(archive.read(members[0]), exchange)
    # Reject HTML, format changes, truncated responses, and empty successes.
    minimum = 50 if exchange == "KONEX" else 300
    if len(rows) < minimum:
        raise ValueError(f"종목마스터 건수 부족: {len(rows)}")
    return rows


def valid_snapshot(value: dict, market: str, now: datetime) -> bool:
    try:
        at = datetime.fromisoformat(value["generated_at"])
        return (value["market"] == market and at.tzinfo is not None and at <= now
                and isinstance(value["symbols"], list) and isinstance(value["sources"], dict))
    except (KeyError, TypeError, ValueError):
        return False


def refresh_directory(output_dir: str | Path = "docs/data", *, now=None, fetcher=fetch_master,
                      previous: dict | None = None, public=True) -> dict:
    now = now or datetime.now(timezone.utc)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for market in ("us", "kr"):
        filename = f"stock-symbols-{market}.json"
        candidates = []
        for value in [(previous or {}).get(market)]:
            if value and valid_snapshot(value, market, now): candidates.append(value)
        if (output / filename).exists():
            try:
                value = json.loads((output / filename).read_text())
                if valid_snapshot(value, market, now): candidates.append(value)
            except (ValueError, OSError): pass
        if public:
            try:
                value = json.loads(download(PUBLIC_BASE + filename))
                if valid_snapshot(value, market, now): candidates.append(value)
            except Exception: pass
        # Pick newest per exchange, rather than overwriting newer seed data.
        source_rows, states = {}, {}
        for exchange, (source_market, _, _) in SOURCES.items():
            if source_market != market: continue
            choices = []
            for candidate in candidates:
                state = candidate["sources"].get(exchange) or {}
                try:
                    at = datetime.fromisoformat(state["observed_at"])
                    rows = [row for row in candidate["symbols"] if row.get("exchange") == exchange]
                    if at.tzinfo and at <= now and rows: choices.append((at, state, rows))
                except (ValueError, KeyError, TypeError): pass
            if choices:
                _, states[exchange], source_rows[exchange] = max(choices, key=lambda item: item[0])
        snapshots[market] = {"market": market, "source_rows": source_rows, "states": states}

    def refresh(exchange):
        market, filename, label = SOURCES[exchange]
        old = snapshots[market]["states"].get(exchange) or {}
        old_rows = snapshots[market]["source_rows"].get(exchange, [])
        # A directory needs daily updates, not thousands of quote requests hourly.
        age = (now - datetime.fromisoformat(old["observed_at"])).total_seconds() if old.get("observed_at") else None
        if old_rows and age is not None and 0 <= age < 86400:
            return exchange, old_rows, old
        try:
            rows = fetcher(exchange)
            if not rows: raise ValueError("빈 종목목록")
            state = {"label": label, "url": BASE + filename + ".zip", "observed_at": now.isoformat(), "status": "정상", "cached": False}
            return exchange, rows, state
        except Exception as exc:
            state = {**old, "label": label, "url": BASE + filename + ".zip", "attempted_at": now.isoformat(),
                     "status": f"목록 갱신 실패 · {type(exc).__name__}", "cached": bool(old_rows)}
            return exchange, old_rows, state

    with ThreadPoolExecutor(max_workers=3) as pool:
        for exchange, rows, state in pool.map(refresh, SOURCES):
            market = SOURCES[exchange][0]
            snapshots[market]["source_rows"][exchange] = rows
            snapshots[market]["states"][exchange] = state
    result = {}
    for market, snapshot in snapshots.items():
        result[market] = {"schema_version": 1, "market": market, "generated_at": now.isoformat(),
                          "source": "한국투자증권 공개 종목마스터", "sources": snapshot["states"],
                          "symbols": [row for rows in snapshot["source_rows"].values() for row in rows]}
        (output / f"stock-symbols-{market}.json").write_text(json.dumps(result[market], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{market}: 종목 검색목록 {len(result[market]['symbols'])}개 · " + " / ".join(f"{key}: {state['status']}" for key, state in snapshot["states"].items()))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/data")
    args = parser.parse_args()
    refresh_directory(args.output)
