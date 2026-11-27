from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from src.stock_symbols import parse_master, refresh_directory, valid_snapshot


class StockDirectoryTests(unittest.TestCase):
    def test_korean_bytes_and_types(self):
        def row(code, name, group):
            return code.encode().ljust(9) + b"KR7000000000" + name.encode("cp949").ljust(40) + group.encode() + b"0"*200
        raw = b"\n".join([row("005930", "삼성전자", "ST"), row("0001A0", "한글신규종목", "ST"),
                           row("Q500067", "신한 ETN", "EN"), row("F70100034", "비상장 펀드", "BC"),
                           row("069500", "KODEX 200", "EF")])
        result = {row['symbol']: row for row in parse_master(raw, "KOSPI")}
        self.assertEqual(set(result), {"005930", "0001A0", "Q500067", "069500"})
        self.assertEqual(result["005930"]["name"], "삼성전자")
        self.assertEqual(result["069500"]["kind"], "ETF")

    def test_us_preserves_names_classes_and_exchange(self):
        raw = ("US\t21\tNYS\t뉴욕\tBRK/B\tNYSBRK/B\t버크셔\tBERKSHIRE B\t2\tUSD\n"
               "US\t21\tNYS\t뉴욕\tAAA\tNYSAAA\tETF 한글\tFUND NAME\t3\tUSD\n"
               "US\t22\tNAS\t나스닥\tWMT\tNASWMT\t월마트\tWALMART\t2\tUSD").encode("cp949")
        rows = parse_master(raw, "NYS")
        self.assertEqual([row["symbol"] for row in rows], ["AAA", "BRK/B"])
        self.assertEqual(rows[1]["english_name"], "BERKSHIRE B")
        self.assertEqual(parse_master(b"<html>unavailable</html>", "NAS"), [])

    def test_refresh_failure_preserves_original_date_and_daily_cache(self):
        now = datetime(2026,11,27,tzinfo=timezone.utc)
        calls=[]
        def fetch(exchange):
            calls.append(exchange)
            return [{"symbol":exchange,"name":"Test", "exchange":exchange}]
        with tempfile.TemporaryDirectory() as directory:
            first=refresh_directory(directory,now=now,fetcher=fetch,public=False)
            self.assertEqual(len(calls),6)
            refresh_directory(directory,now=now+timedelta(hours=23),fetcher=fetch,public=False)
            self.assertEqual(len(calls),6,'daily directory does not call all masters hourly')
            def fail(exchange): raise TimeoutError('provider unavailable')
            failed=refresh_directory(directory,now=now+timedelta(hours=25),fetcher=fail,public=False)
            self.assertEqual(failed['us']['symbols'],first['us']['symbols'])
            self.assertEqual(failed['us']['sources']['NAS']['observed_at'],now.isoformat())
            self.assertTrue(failed['us']['sources']['NAS']['cached'])
            refreshed=refresh_directory(directory,now=now+timedelta(hours=26),fetcher=fetch,public=False)
            self.assertFalse(refreshed['us']['sources']['NAS']['cached'])
            self.assertEqual(refreshed['us']['sources']['NAS']['observed_at'],(now+timedelta(hours=26)).isoformat())

    def test_future_snapshots_rejected(self):
        now=datetime.now(timezone.utc)
        value={'market':'us','generated_at':(now+timedelta(days=1)).isoformat(),'symbols':[],'sources':{}}
        self.assertFalse(valid_snapshot(value,'us',now))
        value['generated_at']=now.replace(tzinfo=None).isoformat()
        self.assertFalse(valid_snapshot(value,'us',now))


if __name__ == '__main__': unittest.main()
