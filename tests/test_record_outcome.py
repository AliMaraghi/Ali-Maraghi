"""scripts/record_outcome.py: list real facts, record a real outcome against one - no inference."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "core"))

import record_outcome  # noqa: E402
from apex.kernel import facts  # noqa: E402
from apex.kernel.memory import Ledger  # noqa: E402


class RecordOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_list_recent_facts_empty_by_default(self):
        self.assertEqual(record_outcome.list_recent_facts(self.ledger), [])

    def test_list_recent_facts_newest_first(self):
        facts.assert_fact(self.ledger, "owner", "a", "1", "src", now=1.0)
        facts.assert_fact(self.ledger, "owner", "b", "2", "src", now=2.0)
        rows = record_outcome.list_recent_facts(self.ledger)
        self.assertEqual([r["predicate"] for r in rows], ["b", "a"])

    def test_list_respects_limit(self):
        for i in range(5):
            facts.assert_fact(self.ledger, "owner", f"p{i}", "v", "src", now=float(i))
        self.assertEqual(len(record_outcome.list_recent_facts(self.ledger, limit=2)), 2)

    def test_recording_an_outcome_against_a_real_fact_works_end_to_end(self):
        fact_id = facts.assert_fact(self.ledger, "owner", "espp_net_gain_pence", "68250", "A-8")
        facts.record_outcome(self.ledger, fact_id, "accepted", note="sold the shares")
        self.assertEqual(facts.outcomes_for(self.ledger, fact_id)[0]["outcome"], "accepted")


if __name__ == "__main__":
    unittest.main()
