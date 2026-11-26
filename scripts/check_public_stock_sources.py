"""Small public-only deployment diagnostic. Does not load secrets or accounts."""
import json
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.stock_public_research import HEADERS, parse_earnings, request_timeout


def main():
    today = datetime.now(ZoneInfo("America/New_York")).date()
    urls = {"earnings": f"https://api.nasdaq.com/api/calendar/earnings?date={today}",
            "ipo": f"https://api.nasdaq.com/api/ipo/calendar?date={today:%Y-%m}",
            "sec_submissions": "https://data.sec.gov/submissions/CIK0000320193.json",
            "sec_facts": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"}
    def check(item):
        key, url = item
        result = {"source": key}
        try:
            response = requests.get(url, headers=HEADERS, timeout=request_timeout(url))
            result["http_status"] = response.status_code
            if response.ok:
                payload = response.json()
                status = payload.get("status") or {}
                result["provider_status"] = status.get("rCode") if isinstance(status, dict) else str(status)[:15]
                if key == "earnings":
                    result["as_of"] = str((payload.get("data") or {}).get("asOf", ""))[:50]
                    try: result["valid_rows"] = len(parse_earnings(payload, today))
                    except ValueError as error: result["parse_error"] = str(error)
                elif key == "ipo":
                    data = payload.get("data") or {};result["period"] = [data.get("year"),data.get("month")]
                    result["valid_data"] = bool(data)
                else:
                    result["cik"] = payload.get("cik")
                    result["valid_data"] = bool(payload.get("facts") or payload.get("filings"))
        except (requests.RequestException, ValueError) as error:
            result["error_type"] = type(error).__name__
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(check, urls.items()): print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
