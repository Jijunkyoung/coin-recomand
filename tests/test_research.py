import copy
import unittest
from datetime import datetime, timedelta, timezone

from src.research import COSTS, VERSION, features, net_return, settle, summary, train, update


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def report(at=NOW):
    return {"generated_at": at.isoformat(), "market": {"regime": "상승", "bitcoin": {"return_7d": 2}},
            "alt_rankings": [{"market": "KRW-ETH", "symbol": "ETH", "price": 100, "ema20": 90,
                              "ema50": 80, "rsi": 55, "return_7d": 8, "trade_value_24h": 2e9,
                              "community_mentions": {"reddit": 4, "coinpan": 5},
                              "community_exposure_rate": 3, "decision": "분할매수 후보", "score": 90,
                              "tokenomics": {"unlock_data_available": True, "next_unlock": None}}],
            "major_events": [{"official_source": True, "related_symbols": ["ETH"], "source_url": "https://example.org/a"}]}


class ResearchTests(unittest.TestCase):
    def test_costs_are_two_sided_and_double_costs_are_worse(self):
        self.assertLess(net_return(100, 100, COSTS), 0)
        self.assertLess(net_return(100, 110, {k:v*2 for k,v in COSTS.items()}), net_return(100, 110, COSTS))

    def test_idempotency_daily_lock_and_next_snapshot_entry(self):
        state = update({}, report(), {"KRW-ETH":100,"KRW-BTC":100})
        original = copy.deepcopy(state)
        self.assertEqual(update(state, report(), {}), original)
        state = update(state, report(NOW+timedelta(hours=1)), {"KRW-ETH":101,"KRW-BTC":100})
        self.assertEqual(len(state["records"]), 1)
        self.assertEqual(state["records"][0]["entry_price"], 101)
        self.assertEqual(state["records"][0]["observed_at"], NOW.isoformat())
        self.assertEqual(state["records"][0]["features"], original["records"][0]["features"])

    def test_entry_missing_not_zero_or_late_fill(self):
        state=update({},report(),{})
        update(state,report(NOW+timedelta(hours=7)),{"KRW-ETH":100,"KRW-BTC":100})
        self.assertEqual(state["records"][0]["status"],"entry_missing")
        row=next(r for r in summary(state)["comparisons"] if r["strategy"]=="existing" and r["days"]==3)
        self.assertEqual(row["missing"],1)
        self.assertIsNone(row["mean_net_pct"])

    def test_exit_uses_actual_time_and_missing_not_survivor_drop(self):
        state=update({},report(),{})
        r=state["records"][0]
        settle(r,{"KRW-ETH":100,"KRW-BTC":100},NOW+timedelta(hours=1))
        settle(r,{"KRW-ETH":110,"KRW-BTC":105},NOW+timedelta(days=1,hours=1))
        self.assertAlmostEqual(r["outcomes"]["1"]["net_pct"], net_return(100,110,COSTS))
        settle(r,{},NOW+timedelta(days=3,hours=8))
        self.assertEqual(r["outcomes"]["3"]["status"],"price_missing")
        self.assertEqual(len(state["records"]),1)

    def test_attention_requires_comparable_sources_and_verified_unlock(self):
        doc=report(); coin=doc["alt_rankings"][0]
        prior={"KRW-ETH":{"exposure":1,"sources":["coinpan","reddit"]}}
        self.assertEqual(features(coin,doc,prior)["attention_growth"],3)
        coin["community_mentions"]["reddit"]=None
        self.assertIsNone(features(coin,doc,prior)["attention_growth"])
        coin["tokenomics"]={}
        self.assertFalse(features(coin,doc,prior)["risk_pass"])

    def test_daily_attention_signal_and_no_lookahead_baseline(self):
        first=report(); first["alt_rankings"][0]["community_exposure_rate"]=1
        state=update({},first,{})
        state=update(state,report(NOW+timedelta(days=1)),{})
        self.assertIn("attention_news",state["records"][-1]["strategies"])
        self.assertNotIn("attention_news",state["records"][0]["strategies"])

    def test_empty_summary_never_invents_performance(self):
        self.assertTrue(all(r["mean_net_pct"] is None for r in summary({})["comparisons"]))

    def test_training_gate_embargo_and_frozen_predictions(self):
        records=[]
        for day in range(70):
            for i in range(4):
                at=NOW+timedelta(days=day)
                records.append({"version":VERSION,"day":at.date().isoformat(),
                                "features":{"relative_7d":i,"attention_growth":i+1},
                                "outcomes":{"3":{"status":"complete","exit_at":(at+timedelta(days=3)).isoformat(),"net_pct":i-1.5}}})
        self.assertIsNone(train(records,NOW+timedelta(days=20))["weights"])
        model=train(records,NOW+timedelta(days=100))
        self.assertIsNotNone(model["weights"])
        self.assertEqual(model["samples"],280)
        future=copy.deepcopy(records[0]);future["outcomes"]["3"]["exit_at"]=(NOW+timedelta(days=101)).isoformat()
        self.assertEqual(train(records+[future],NOW+timedelta(days=100)),model)


if __name__ == "__main__":
    unittest.main()
