import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import commute, itinerary, scout_common, spending_rules as sr
from apex.kernel.budget import Budget
from apex.kernel.memory import Ledger
from apex.sources import public_http

TFL = [{"id": "northern", "name": "Northern", "lineStatuses": [{"statusSeverity": 10, "statusSeverityDescription": "Good Service"}]},
       {"id": "piccadilly", "name": "Piccadilly", "lineStatuses": [{"statusSeverity": 10, "statusSeverityDescription": "Good Service"},
                                                                    {"statusSeverity": 6, "statusSeverityDescription": "Severe Delays", "reason": "Signal  failure at X"}]}]


class Commute(unittest.TestCase):
    def test_reports_tfl_words_and_never_invents_a_route(self):
        seen = []
        out = commute.run({"commute_lines": ["northern", "piccadilly"]}, lambda url: seen.append(url) or json.dumps(TFL).encode(), 1.0)
        self.assertEqual(seen, ["https://api.tfl.gov.uk/Line/northern,piccadilly/Status"])
        self.assertEqual([(x["name"], x["state"], x["good"]) for x in out["lines"]], [("Northern", "Good Service", True), ("Piccadilly", "Severe Delays", False)])
        self.assertEqual((out["all_good"], out["lines"][1]["reason"]), (False, "Signal failure at X"))
        self.assertEqual(commute.run({}, None)["status"], "NO_LINES_SET")
        self.assertTrue(commute.run({"commute_lines": ["northern"]}, lambda url: 1 / 0)["status"].startswith("UNAVAILABLE"))

    def test_only_the_status_path_is_allowed_and_lines_save_privately(self):
        public_http.validate("https://api.tfl.gov.uk/Line/piccadilly,northern,elizabeth/Status")
        for bad in ("https://api.tfl.gov.uk/Line/northern/Status?app_key=x", "https://api.tfl.gov.uk/Journey/JourneyResults/a/to/b"):
            with self.assertRaises(public_http.SourceError):
                public_http.validate(bad)
        root = Path(tempfile.mkdtemp())
        self.assertEqual(scout_common.save_groups(root, ["northern", "elizabeth"], "commute_lines"), 2)
        self.assertEqual(scout_common.load_config(root)["commute_lines"], ["northern", "elizabeth"])
        with self.assertRaises(ValueError):
            scout_common.save_groups(root, ["x"], "profile")


class Spike(unittest.TestCase):
    def test_only_a_week_30_percent_over_its_four_week_average_asks(self):
        weeks = {f"2026-10-{d:02d}": 5000 for d in (5, 12, 19, 26)}
        self.assertIsNone(sr.food_spike({"weekly_food_pence": {**weeks, "2026-11-02": 6400}}))
        spike = sr.food_spike({"weekly_food_pence": {**weeks, "2026-11-02": 9000}})
        self.assertEqual((spike["week_start"], spike["percent_above"], spike["average_pence"]), ("2026-11-02", 80, 5000))
        self.assertIn("worth noting", spike["question"])
        self.assertIsNone(sr.food_spike({"weekly_food_pence": {"2026-11-02": 9000}}))


class Itinerary(unittest.TestCase):
    def test_outline_drops_lines_with_numbers_and_bad_requests(self):
        ledger = Ledger(Path(tempfile.mkdtemp()))
        budget = Budget(ledger)
        budget.set_price(scout_common.PROVIDER, scout_common.SKU, 2000, 1.0, "test")
        budget.set_cap(scout_common.POOL, "day", 100)
        reply = {"days": [{"morning": "Walk the old town", "afternoon": "Museum, tickets 12 euros", "evening": "Dinner by the river"}, {"morning": "Market"}]}
        out = itinerary.plan(lambda s, u, m: json.dumps(reply), budget, "Lisbon", 2, "food", 1.0)
        self.assertEqual(out["days"], [{"morning": "Walk the old town", "evening": "Dinner by the river"}, {"morning": "Market"}])
        self.assertEqual(itinerary.plan(None, budget, "", 2)["status"], "BAD_REQUEST")
        self.assertEqual(itinerary.plan(None, budget, "Rome", 9)["status"], "BAD_REQUEST")
        ledger.close()


if __name__ == "__main__":
    unittest.main()
