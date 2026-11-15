"""Approval-tiering policy layer (brutal-honesty directive, 2026-11-15, section 4). All
synthetic fixtures - no real owner data. Proves the three required invariants: (1) a
read-only/informational kind can be classified always_allow, (2) a money/communication/
system-change kind can NEVER be anything but always_ask, no matter what, and (3) every
tiering decision is journaled with its policy reason. It also proves the deeper invariant
underneath all three: tiering never calls ApprovalBook.issue()/approve() - a proposal stays
PENDING regardless of its tier, exactly as before this module existed."""
import json
import tempfile
import unittest
from pathlib import Path

from apex.kernel import tiering
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS, KindSpec
from apex.kernel.memory import Ledger

SECRET = b"k" * 32


class TierClassificationTests(unittest.TestCase):
    def test_a_readonly_informational_kind_is_always_allow(self):
        decision = tiering.tier_for("record_decision", DEFAULT_KINDS["record_decision"])
        self.assertEqual(decision.tier, tiering.ALWAYS_ALLOW)
        self.assertTrue(decision.reason)

    def test_research_brief_proposal_is_also_always_allow(self):
        decision = tiering.tier_for("research_brief_proposal", DEFAULT_KINDS["research_brief_proposal"])
        self.assertEqual(decision.tier, tiering.ALWAYS_ALLOW)

    def test_money_kind_is_permanently_always_ask(self):
        decision = tiering.tier_for("finance_action_proposal", DEFAULT_KINDS["finance_action_proposal"])
        self.assertEqual(decision.tier, tiering.ALWAYS_ASK)
        self.assertIn("PINNED", decision.reason)

    def test_capability_growth_kind_is_permanently_always_ask(self):
        decision = tiering.tier_for("capability_proposal", None)
        self.assertEqual(decision.tier, tiering.ALWAYS_ASK)
        self.assertIn("PINNED", decision.reason)

    def test_any_adapter_backed_kind_defaults_to_always_ask(self):
        for name in ("telegram_notify", "gmail_draft", "outlook_draft", "laptop_browser_task", "mock_notify"):
            decision = tiering.tier_for(name, DEFAULT_KINDS[name])
            self.assertEqual(decision.tier, tiering.ALWAYS_ASK, name)

    def test_a_brand_new_unlisted_kind_defaults_to_always_ask_not_always_allow(self):
        """The default-deny invariant: a kind this module has never seen (e.g. added to the
        Gateway tomorrow) is always_ask until someone deliberately allowlists it - the
        allowlist is not something tiering can infer or widen on its own."""
        spec = KindSpec(frozenset({"opportunity"}), {"x": str})
        decision = tiering.tier_for("brand_new_kind_nobody_reviewed_yet", spec)
        self.assertEqual(decision.tier, tiering.ALWAYS_ASK)

    def test_pinning_cannot_be_overridden_by_passing_a_spec_with_no_adapter(self):
        """Even if a caller constructs a KindSpec for 'finance_action_proposal' with
        adapter=None (as the real one is), the PINNED kind-name check still wins - tiering is
        never fooled by a caller's own KindSpec."""
        fake_spec = KindSpec(frozenset({"personal"}), {"x": str}, adapter=None)
        decision = tiering.tier_for("finance_action_proposal", fake_spec)
        self.assertEqual(decision.tier, tiering.ALWAYS_ASK)


class TieringNeverApprovesTests(unittest.TestCase):
    """The invariant underneath all three required proofs: tiering only classifies and
    journals - it never calls issue()/approve(), so every proposal of every tier still sits
    PENDING for a real human, exactly as before this module existed."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.book = ApprovalBook(self.ledger, SECRET, clock=lambda: 1_800_000_000.0)
        self.gateway = ActionGateway(self.ledger, self.book, Budget(self.ledger))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_always_allow_classified_proposal_still_sits_pending(self):
        state = self.gateway.submit("p1", "opportunity", "record_decision", "agent:test",
                                     {"note": "a harmless local note"}, ["fact:1"])
        decision = tiering.tier_for("record_decision", self.gateway.kinds["record_decision"])
        self.assertEqual(decision.tier, tiering.ALWAYS_ALLOW)
        tiering.journal_decision(self.ledger, "p1", "opportunity", decision)
        # tiering ran; the proposal is STILL exactly what ApprovalBook.propose() left it as.
        self.assertEqual(state, "PENDING")
        self.assertEqual(self.book.view("p1")["state"], "PENDING")
        with self.assertRaises(Exception):
            self.gateway.execute("p1")   # not APPROVED - tiering never approved it

    def test_tiering_module_has_no_reference_to_issue_or_approve(self):
        """AST-level check of actual code (not the module's own docstrings, which explain
        issue()/approve() in prose): no Call node anywhere in tiering.py invokes a method
        named issue or approve."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(tiering))
        called_names = {node.func.attr for node in ast.walk(tree)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("issue", called_names)
        self.assertNotIn("approve", called_names)

    def test_decision_is_journaled_with_its_reason_and_is_idempotent(self):
        self.gateway.submit("p2", "opportunity", "research_brief_proposal", "agent:test",
                             {"topic": "x", "draft": "y", "critic_notes": "z"}, ["fact:1"])
        decision = tiering.tier_for("research_brief_proposal", self.gateway.kinds["research_brief_proposal"])
        seq1 = tiering.journal_decision(self.ledger, "p2", "opportunity", decision)
        seq2 = tiering.journal_decision(self.ledger, "p2", "opportunity", decision)   # idempotent re-journal
        self.assertEqual(seq1, seq2)
        rows = [json.loads(r[0]) for r in self.ledger.db.execute(
            "SELECT payload FROM events WHERE event_key LIKE 'tier.%'")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], tiering.ALWAYS_ALLOW)
        self.assertIn("allowlist", rows[0]["reason"])


if __name__ == "__main__":
    unittest.main()
