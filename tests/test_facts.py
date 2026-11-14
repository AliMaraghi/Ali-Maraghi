"""Append-only fact store with provenance + outcome tracking (core/apex/kernel/facts.py)."""
import tempfile
import time
import unittest
from pathlib import Path

from apex.kernel import facts
from apex.kernel.memory import Ledger


class FactStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_query_before_any_assertion_is_none(self):
        self.assertIsNone(facts.query_fact(self.ledger, "owner", "espp_net_gain_pence"))

    def test_assert_then_query_returns_the_latest(self):
        facts.assert_fact(self.ledger, "owner", "espp_net_gain_pence", "54600", "A-8", now=100.0)
        facts.assert_fact(self.ledger, "owner", "espp_net_gain_pence", "68250", "A-8", now=200.0)
        current = facts.query_fact(self.ledger, "owner", "espp_net_gain_pence")
        self.assertEqual(current["object"], "68250")
        self.assertEqual(current["asserted_at"], 200.0)

    def test_history_keeps_every_assertion_newest_first(self):
        facts.assert_fact(self.ledger, "owner", "x", "a", "src", now=1.0)
        facts.assert_fact(self.ledger, "owner", "x", "b", "src", now=2.0)
        facts.assert_fact(self.ledger, "owner", "x", "c", "src", now=3.0)
        history = facts.fact_history(self.ledger, "owner", "x")
        self.assertEqual([h["object"] for h in history], ["c", "b", "a"])

    def test_contradicting_assertions_are_both_kept_not_silently_overwritten(self):
        facts.assert_fact(self.ledger, "owner", "city", "London", "voice", now=1.0)
        facts.assert_fact(self.ledger, "owner", "city", "Paris", "voice", now=2.0)
        history = facts.fact_history(self.ledger, "owner", "city")
        self.assertEqual(len(history), 2)
        self.assertEqual(facts.query_fact(self.ledger, "owner", "city")["object"], "Paris")

    def test_empty_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            facts.assert_fact(self.ledger, "", "x", "y", "src")
        with self.assertRaises(ValueError):
            facts.assert_fact(self.ledger, "owner", "x", "y", "")

    def test_record_outcome_and_read_it_back(self):
        fact_id = facts.assert_fact(self.ledger, "owner", "espp_net_gain_pence", "68250", "A-8")
        facts.record_outcome(self.ledger, fact_id, "accepted", note="sold the shares")
        outcomes = facts.outcomes_for(self.ledger, fact_id)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["outcome"], "accepted")
        self.assertEqual(outcomes[0]["note"], "sold the shares")

    def test_invalid_outcome_value_is_rejected(self):
        fact_id = facts.assert_fact(self.ledger, "owner", "x", "y", "src")
        with self.assertRaises(ValueError):
            facts.record_outcome(self.ledger, fact_id, "maybe")

    def test_a_fact_with_no_recorded_outcome_returns_empty_list(self):
        fact_id = facts.assert_fact(self.ledger, "owner", "x", "y", "src")
        self.assertEqual(facts.outcomes_for(self.ledger, fact_id), [])


if __name__ == "__main__":
    unittest.main()


class CalibrationHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_empty_when_no_outcomes_recorded(self):
        facts.assert_fact(self.ledger, "owner", "finance_claim_0", "gain 100p", "A-8")
        self.assertEqual(facts.recent_outcomes_for_predicate_prefix(self.ledger, "owner", "finance_claim_"), [])

    def test_finds_outcomes_by_prefix_only(self):
        fid1 = facts.assert_fact(self.ledger, "owner", "finance_claim_0", "gain 100p", "A-8", now=1.0)
        fid2 = facts.assert_fact(self.ledger, "owner", "academic_claim_0", "some paper", "A-1", now=2.0)
        facts.record_outcome(self.ledger, fid1, "rejected", note="too conservative", now=3.0)
        facts.record_outcome(self.ledger, fid2, "accepted", now=4.0)
        rows = facts.recent_outcomes_for_predicate_prefix(self.ledger, "owner", "finance_claim_")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "rejected")
        self.assertEqual(rows[0]["note"], "too conservative")

    def test_newest_outcome_first(self):
        fid = facts.assert_fact(self.ledger, "owner", "finance_claim_0", "gain 100p", "A-8")
        facts.record_outcome(self.ledger, fid, "rejected", note="first", now=1.0)
        facts.record_outcome(self.ledger, fid, "accepted", note="second", now=2.0)
        rows = facts.recent_outcomes_for_predicate_prefix(self.ledger, "owner", "finance_claim_")
        self.assertEqual(rows[0]["note"], "second")


if __name__ == "__main__":
    unittest.main()


class ContradictionScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_no_facts_no_contradictions(self):
        self.assertEqual(facts.find_contradictions(self.ledger), [])

    def test_single_assertion_is_not_a_contradiction(self):
        facts.assert_fact(self.ledger, "owner", "city", "London", "voice")
        self.assertEqual(facts.find_contradictions(self.ledger), [])

    def test_repeated_identical_value_is_not_a_contradiction(self):
        facts.assert_fact(self.ledger, "owner", "city", "London", "voice", now=1.0)
        facts.assert_fact(self.ledger, "owner", "city", "London", "voice", now=2.0)
        self.assertEqual(facts.find_contradictions(self.ledger), [])

    def test_two_distinct_values_is_a_contradiction_with_full_history(self):
        facts.assert_fact(self.ledger, "owner", "city", "London", "voice", now=1.0)
        facts.assert_fact(self.ledger, "owner", "city", "Paris", "voice", now=2.0)
        out = facts.find_contradictions(self.ledger)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["subject"], out[0]["predicate"]), ("owner", "city"))
        self.assertEqual([h["object"] for h in out[0]["history"]], ["Paris", "London"])

    def test_different_subjects_or_predicates_never_mix(self):
        facts.assert_fact(self.ledger, "owner", "city", "London", "voice", now=1.0)
        facts.assert_fact(self.ledger, "owner", "city", "Paris", "voice", now=2.0)
        facts.assert_fact(self.ledger, "owner", "country", "UK", "voice", now=1.0)
        facts.assert_fact(self.ledger, "someone_else", "city", "Rome", "voice", now=1.0)
        out = facts.find_contradictions(self.ledger)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
