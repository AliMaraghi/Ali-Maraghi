import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from datetime import date
from apex import deterministic_classifier as dc, spending_rules as sr


class CategorySpikes(unittest.TestCase):
    def test_summary_keeps_weekly_series_and_income(self):
        tx = [{"description": "DELIVEROO", "pence": -5000, "date": date(2026, 11, 2)},
              {"description": "TESCO STORES", "pence": -3000, "date": date(2026, 11, 3)},
              {"description": "UNIVERSAL CREDIT", "pence": 90000, "date": date(2026, 11, 4)}]
        out = dc.summarise(tx)
        self.assertEqual(out["weekly_category_pence"]["Food delivery"], {"2026-11-02": 5000})
        self.assertEqual(out["weekly_in_pence"], {"2026-11-02": 90000})

    def test_spike_needs_history_ratio_and_size(self):
        series = {f"2026-10-{d:02d}": 5000 for d in (5, 12, 19, 26)}
        rec = {"weekly_category_pence": {"Food delivery": {**series, "2026-11-02": 9000}, "Cash": {**series, "2026-11-02": 5500}}}
        spikes = sr.category_spikes(rec)
        self.assertEqual([s["category"] for s in spikes], ["Food delivery"])
        self.assertEqual(spikes[0]["percent_above"], 80)
        self.assertIn("Food delivery came to 90.00", sr.top_spike(rec)["question"])
        self.assertEqual(sr.category_spikes({"weekly_category_pence": {"Cash": {"2026-11-02": 9000}}}), [])

    def test_payday_effect_reports_counts_without_cause(self):
        weeks = [f"2026-{m:02d}-{d:02d}" for m, d in ((9, 7), (9, 14), (9, 21), (9, 28), (10, 5), (10, 12), (10, 19), (10, 26), (11, 2))]
        rec = {"weekly_in_pence": {w: (100000 if i % 3 == 0 else 1000) for i, w in enumerate(weeks)},
               "weekly_category_pence": {"Groceries": {w: (20000 if i % 3 == 0 else 8000) for i, w in enumerate(weeks)}}}
        res = sr.payday_effect(rec)
        self.assertEqual((res["weeks"], res["high_income_weeks"], res["avg_out_high_income_pence"], res["avg_out_other_pence"]), (9, 3, 20000, 8000))
        self.assertIsNone(sr.payday_effect({"weekly_in_pence": {}, "weekly_category_pence": {}}))


if __name__ == "__main__":
    unittest.main()
