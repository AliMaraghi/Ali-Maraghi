"""Offline tests: sourced CGT arithmetic, the example rules file, and official-API rate pacing."""
import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from apex import social_pacing
from apex.agents_impl import capital_gains_tax, uc_capital_deduction

RULES = json.loads((Path(__file__).resolve().parents[1] / "examples" / "uk_tax_rules.cgt_uc.example.json").read_text())


class CgtTests(unittest.TestCase):
    def test_govuk_worked_examples(self):
        # gov.uk 2026-27 example: 12,600 gain, 20,000 taxable income -> 9,600 at 18% = 1,728
        self.assertEqual(capital_gains_tax(1_260_000, 0, 2_000_000, RULES), 172_800)
        self.assertEqual(capital_gains_tax(300_000, 0, 0, RULES), 0)                    # inside the exempt amount
        self.assertEqual(capital_gains_tax(2_000_000, 0, 8_000_000, RULES), 408_000)    # all at 24%
        # straddles the band: 1,000 of band left at 18%, remaining 9,000 at 24%
        self.assertEqual(capital_gains_tax(1_300_000, 0, 3_670_000, RULES), 18_000 + 216_000)
        self.assertEqual(capital_gains_tax(1_000_000, 800_000, 0, RULES), 0)            # losses first

    def test_no_rules_no_number_and_bad_input_refused(self):
        self.assertEqual(capital_gains_tax(1, 0, 0, {}), "NOT_MODELLED")
        for bad in ((-1, 0, 0), (1.5, 0, 0), (1, 0, True)):
            with self.assertRaises(ValueError):
                capital_gains_tax(*bad, RULES)

    def test_example_uc_figures_match_published_examples(self):
        self.assertEqual(uc_capital_deduction(600_000, RULES), 0)
        self.assertEqual(uc_capital_deduction(650_000, RULES), 870)        # 6,500 -> 2 x 4.35
        self.assertEqual(uc_capital_deduction(811_000, RULES), 3_915)      # 8,110 -> 9 x 4.35
        self.assertIsNone(uc_capital_deduction(1_600_001, RULES))          # over 16,000: not entitled


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.db, self.now = sqlite3.connect(":memory:"), [1_800_000_000.0]
        self.limit = social_pacing.Limit("test-api", 10, 3600, "test fixture", "2026-11-17")
        self.pacer = social_pacing.Pacer(self.db, self.limit, clock=lambda: self.now[0])

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(social_pacing.FLAG, None)
            with self.assertRaisesRegex(social_pacing.PacingDenied, "not enabled"):
                self.pacer.acquire()

    def test_even_spacing_and_window_ceiling_survive_restart(self):
        with mock.patch.dict(os.environ, {social_pacing.FLAG: "true"}):
            self.pacer.acquire()
            with self.assertRaisesRegex(social_pacing.PacingDenied, "RATE_PACED"):
                self.pacer.acquire()                                   # no bursts
            sent = 1
            for _ in range(40):
                self.now[0] += 60
                restarted = social_pacing.Pacer(self.db, self.limit, clock=lambda: self.now[0])
                try:
                    restarted.acquire()
                    sent += 1
                except social_pacing.PacingDenied:
                    pass
            self.assertLessEqual(sent, 8)                              # 80% of the documented 10 an hour
            recent = self.db.execute("SELECT COUNT(*) FROM api_pacing WHERE at>?", (self.now[0] - 3600,)).fetchone()[0]
            self.assertLessEqual(recent, 8)

    def test_limit_needs_a_source(self):
        with self.assertRaises(ValueError):
            social_pacing.Limit("x", 10, 3600, "", "2026-11-17")


if __name__ == "__main__":
    unittest.main()
