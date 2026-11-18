import sys, unittest
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import deterministic_classifier as dc, spending_rules as sr


class Classifier(unittest.TestCase):
    def test_rules_are_fixed_and_unknown_is_never_guessed(self):
        self.assertEqual([dc.classify(d) for d in ("UBER * EATS PENDING", "UBER TRIP HELP.UBER.COM", "Pret A Manger", "TESCO STORES 5861",
                                                   "202S8158W DWP UC", "Costa Coffee Edgware", "ZZZ UNKNOWN LTD")],
                         ["Food delivery", "Transport", "Eating out & coffee", "Groceries", "Benefits: Universal Credit",
                          "Eating out & coffee", dc.OTHER])

    def test_owner_rules_stay_in_a_private_file_and_apply_first(self):
        import json, tempfile
        root = Path(tempfile.mkdtemp())
        self.assertEqual(dc.load_private_rules(root), ())
        path = root.joinpath(*dc.PRIVATE_RULES)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"rules": [["Salary", ["acme widgets co"]], ["Food delivery", ["corner tiffin"]]]}))
        extra = dc.load_private_rules(root)
        self.assertEqual((dc.classify("ACME WIDGETS CO 123", extra), dc.classify("Corner Tiffin London", extra), dc.classify("ACME WIDGETS CO 123")),
                         ("Salary", "Food delivery", dc.OTHER))
        for bad in ([["Nonsense", ["X1"]]], [["Salary", []]], "x", [["Salary", ["a"]]]):
            with self.assertRaises(ValueError):
                dc.check_rules(bad)

    def test_card_export_with_positive_spend_is_turned_round(self):
        rows = [{"description": d, "pence": 500, "date": date(2026, 11, 16)} for d in ("TESCO", "PRET A MANGER", "DELIVEROO", "LIDL GB", "JUST EAT")]
        rows.append({"description": "PAYMENT RECEIVED - THANK YOU", "pence": -2500, "date": date(2026, 11, 17)})
        out = dc.summarise(rows)
        self.assertTrue(out["signs_flipped"])
        self.assertEqual((out["totals"]["Groceries"]["out_pence"], out["weekly_food_pence"]), (1000, {"2026-11-16": 1500}))

    def test_reconciles_against_printed_balances_either_order(self):
        rows = [{"description": "A", "pence": -1000, "balance_pence": 9000}, {"description": "B", "pence": -500, "balance_pence": 8500}]
        self.assertEqual(dc.reconcile(rows)["status"], "OK")
        self.assertEqual(dc.reconcile(rows[::-1])["status"], "OK")
        rows[1]["balance_pence"] = 8400
        self.assertEqual(dc.reconcile(rows)["status"], "MISMATCH")
        self.assertEqual(dc.reconcile([{"description": "A", "pence": 1}])["status"], "NO_BALANCES")


class FoodRule(unittest.TestCase):
    def summary(self, day, pence):
        return dc.summarise([{"description": "DELIVEROO", "pence": -pence, "date": day}])

    def test_alert_names_its_week_and_flags_old_data(self):
        record = sr.merge(None, "card.csv", self.summary(date(2026, 11, 17), 12000), 0)
        record = sr.merge(record, "current.csv", self.summary(date(2026, 11, 18), 1000), 0)
        now = datetime(2026, 11, 19).timestamp()
        alert = sr.food_alert(record, 10000, now)
        self.assertEqual((alert["week_start"], alert["current_pence"], alert["exceeded"], alert["stale"]), ("2026-11-16", 13000, True, False))
        self.assertTrue(sr.food_alert(record, 10000, datetime(2027, 1, 19).timestamp())["stale"])
        self.assertIsNone(sr.food_alert(None))
        # the same file uploaded again replaces its own totals instead of doubling them
        again = sr.merge(record, "card.csv", self.summary(date(2026, 11, 17), 12000), 0)
        self.assertEqual(sr.food_alert(again, 10000, now)["current_pence"], 13000)
        self.assertIn("Food delivery", sr.digest(record))


if __name__ == "__main__":
    unittest.main()
