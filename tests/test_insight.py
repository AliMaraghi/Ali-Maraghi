import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import insight


def rec(n=12):
    weeks = [f"2026-{(i // 4) + 1:02d}-{(i % 4) * 7 + 1:02d}" for i in range(n)]
    income = {w: (100000 if i % 3 == 0 else 20000) for i, w in enumerate(weeks)}
    delivery = {w: (30000 if i % 3 == 0 else 5000) for i, w in enumerate(weeks)}
    rent = {w: 10000 for w in weeks}
    return {"weekly_in_pence": income, "weekly_category_pence": {"Food delivery": delivery, "Housing & council": rent}}


class Insight(unittest.TestCase):
    def test_needs_enough_weeks(self):
        self.assertIsNone(insight.economics(rec(5)))
        self.assertIsNone(insight.graph(rec(5)))
        self.assertEqual(insight.behaviour(rec(5)), [])

    def test_economics_numbers(self):
        e = insight.economics(rec())
        self.assertEqual(e["weeks"], 12)
        self.assertEqual(e["essential_share_pct"], round(100 * 120000 / (120000 + 4 * 30000 + 8 * 5000)))
        self.assertEqual(e["top3"][0]["category"], "Food delivery")

    def test_behaviour_finds_payday_and_convenience(self):
        names = [b["name"] for b in insight.behaviour(rec())]
        self.assertIn("Spending rises in weeks money arrives", names)

    def test_graph_links_delivery_to_income(self):
        g = insight.graph(rec())
        self.assertTrue(any({e["a"], e["b"]} == {"Income", "Food delivery"} for e in g["edges"]))
        self.assertFalse(any("Housing & council" in (e["a"], e["b"]) for e in g["edges"]))  # constant series: no correlation


if __name__ == "__main__":
    unittest.main()
