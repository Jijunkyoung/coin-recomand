"""Refresh public-only reference observations from an allowed execution host.

No proxy, credentials or account APIs. Failed sources retain their prior
timestamp. Commit the resulting public JSON to publish an updated seed.
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.stock_analysis import load_settings
from src.stock_public_research import CACHE_HOURS, collect_public_research


def main():
    path = Path("config/stock-public-last-success.json")
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "sources": {}}
    result = collect_public_research({}, load_settings())
    for key in CACHE_HOURS:
        source = result["sources"][key]
        rows = [row for target in ("economic_events", "earnings", "filings", "ipos", "reported_earnings") for row in result[target] if row.get("_source") == key]
        if source["status"] == "정상 수집":
            existing["sources"][key] = {"observed_at": source["observed_at"], "source_url": source["url"], "rows": rows}
            print(f"{key}: {len(rows)} public observations saved")
        else:
            print(f"{key}: retrieval failed; existing timestamp retained")
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
