"""Phase 3 capability tokens (brutal-honesty directive, 2026-11-15). All synthetic fixtures.

This exercises the EXISTING kernel.approvals.ApprovalBook issue()/approve() mechanism
directly - the real capability-token system, per capability_tokens.py's own correction of
the Phase 3 prompt's premise - rather than building a second, parallel token system
alongside a working one. Proves the three required forgeability properties (fabricated
token rejected, replayed token rejected, expired token rejected), that a money kind can
never be issued a token through any agent/always-allow path, and that adding a brand-new
kind requires zero edits to approvals.py or ActionGateway.execute()'s enforcement code."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel import capability_tokens, tiering
from apex.kernel.approvals import ApprovalBook, ApprovalError
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS, GatewayError, KindSpec
from apex.kernel.memory import Ledger
from apex.kernel.policy import KillState

SECRET = b"k" * 32


class CapabilityTokenBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = [1_800_000_000.0]
        self.ledger = Ledger(self.root)
        self.book = ApprovalBook(self.ledger, SECRET, clock=lambda: self.now[0])
        self.gateway = ActionGateway(self.ledger, self.book, Budget(self.ledger))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def propose(self, pid="p1", kind="record_decision", domain="opportunity", payload=None):
        payload = payload or {"note": "x"}
        self.gateway.submit(pid, domain, kind, "agent:test", payload, ["fact:1"])
        return pid


class ForgeabilityTests(CapabilityTokenBase):
    def test_a_fabricated_signature_is_rejected(self):
        pid = self.propose()
        token = self.book.issue(pid, "owner")
        nonce, _real_signature = token.split(".", 1)
        forged = f"{nonce}.{'0' * 64}"
        with self.assertRaises(ApprovalError) as ctx:
            self.book.approve(pid, forged, "owner")
        self.assertEqual(str(ctx.exception), "BAD_SIGNATURE")

    def test_a_completely_made_up_token_with_an_unknown_nonce_is_rejected(self):
        pid = self.propose()
        fabricated = "0" * 32 + "." + "0" * 64
        with self.assertRaises(ApprovalError) as ctx:
            self.book.approve(pid, fabricated, "owner")
        self.assertEqual(str(ctx.exception), "UNKNOWN_TOKEN")

    def test_a_replayed_already_used_token_is_rejected(self):
        pid = self.propose()
        token = self.book.issue(pid, "owner")
        self.book.approve(pid, token, "owner")
        with self.assertRaises(ApprovalError) as ctx:
            self.book.approve(pid, token, "owner")
        self.assertEqual(str(ctx.exception), "REPLAY")

    def test_an_expired_token_is_rejected(self):
        pid = self.propose()
        token = self.book.issue(pid, "owner")
        self.now[0] += 20 * 60                    # past APPROVAL_TTL (15 minutes)
        with self.assertRaises(ApprovalError) as ctx:
            self.book.approve(pid, token, "owner")
        self.assertEqual(str(ctx.exception), "TOKEN_EXPIRED")

    def test_a_token_issued_for_one_proposal_does_not_approve_another(self):
        pid1 = self.propose("p1")
        pid2 = self.propose("p2")
        token_for_p1 = self.book.issue(pid1, "owner")
        with self.assertRaises(ApprovalError) as ctx:
            self.book.approve(pid2, token_for_p1, "owner")
        self.assertEqual(str(ctx.exception), "UNKNOWN_TOKEN")

    def test_an_action_without_a_token_cannot_reach_execute(self):
        """The structural check, not a convention: PENDING state alone is not enough -
        execute() unconditionally requires APPROVED, which nothing but a validated token
        from approve() can produce."""
        pid = self.propose()
        with self.assertRaises(GatewayError) as ctx:
            self.gateway.execute(pid)
        self.assertEqual(str(ctx.exception), "NOT_APPROVED")


class MoneyKindTokenTests(CapabilityTokenBase):
    def test_no_agent_identity_can_ever_issue_a_token_for_a_money_kind(self):
        """Money kinds get no special-cased shortcut - the human-identity-only rule in
        issue() applies identically regardless of which kind the proposal is for."""
        pid = self.propose("p-money", kind="finance_action_proposal", domain="personal",
                           payload={"action_name": "exercise_espp_now", "scenario_text": "x",
                                    "gain_pence": 1, "tax_pence": 0, "net_pence_clamped": 1,
                                    "evaluator_verdict": "{}", "fact_id": 0})
        with self.assertRaises(ApprovalError) as ctx:
            self.book.issue(pid, "agent:scheduler")
        self.assertEqual(str(ctx.exception), "HUMAN_IDENTITY_REQUIRED")
        with self.assertRaises(ApprovalError):
            self.book.issue(pid, "agent:test")       # also the proposer itself - still an agent identity
        token = self.book.issue(pid, "owner")         # only a real human identity can ever get this far
        self.assertEqual(self.book.approve(pid, token, "owner"), "APPROVED")

    def test_tiering_always_allow_classification_grants_no_issuance_path_for_any_kind(self):
        """Cross-check against kernel.tiering: an always_allow classification (even for a
        non-money kind) never translates into an issued token - tiering has no reference to
        issue() at all (re-verified structurally here, not just in test_tiering.py)."""
        decision = tiering.tier_for("record_decision", DEFAULT_KINDS["record_decision"])
        self.assertEqual(decision.tier, tiering.ALWAYS_ALLOW)
        pid = self.propose("p-record", kind="record_decision")
        # No code path from `decision` to a token exists - demonstrated by the only way to
        # get one being the real human-gated issue() call below.
        with self.assertRaises(ApprovalError):
            self.book.issue(pid, "agent:whoever")
        token = self.book.issue(pid, "owner")
        self.assertEqual(self.book.approve(pid, token, "owner"), "APPROVED")


class NewKindRequiresNoSecurityModelEditTests(CapabilityTokenBase):
    def test_a_brand_new_kind_works_through_issue_approve_execute_with_zero_edits_to_approvals_py(self):
        """The required Phase 3 gate: adding a new kind needs a DEFAULT_KINDS-style registry
        entry only - approvals.py and ActionGateway.execute()'s enforcement code are
        completely unaware of kind names and need no edit for this to work."""
        new_kind = KindSpec(frozenset({"opportunity"}), {"text": str}, adapter="mock")
        from apex.kernel.gateway import MockAdapter
        budget = Budget(self.ledger, clock=lambda: self.now[0])
        budget.set_price("mock", "echo", 0, self.now[0] - 1, "test")
        gateway = ActionGateway(self.ledger, self.book, budget,
                                adapters={"mock": MockAdapter()},
                                kinds={**DEFAULT_KINDS, "brand_new_phase3_kind": new_kind})
        self.assertTrue(capability_tokens.kind_requires_token(gateway, "brand_new_phase3_kind"))
        pid = "p-new-kind"
        gateway.submit(pid, "opportunity", "brand_new_phase3_kind", "agent:test", {"text": "hello"}, ["fact:1"])
        token = self.book.issue(pid, "owner")
        self.book.approve(pid, token, "owner")
        self.assertEqual(gateway.execute(pid), "EXECUTED")

    def test_kind_requires_token_raises_for_an_unregistered_kind_rather_than_vouching_for_it(self):
        with self.assertRaises(KeyError):
            capability_tokens.kind_requires_token(self.gateway, "nothing_registered_this_name")


if __name__ == "__main__":
    unittest.main()
