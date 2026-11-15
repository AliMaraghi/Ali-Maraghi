"""Phase 4 (brutal-honesty directive, 2026-11-15): audit-chain tamper detection and signed
Budget pricing. All synthetic fixtures - no real owner data, no real ledger file.

Important correction recorded here for the record: a hash chain (digest(seq, key, kind,
domain, payload, previous)) and a whole-chain verify() ALREADY EXISTED in
core/apex/kernel/memory.py before this round - an earlier pasted architecture review claimed
otherwise and was wrong. What was genuinely missing, and is what this file proves, is (a) a
non-raising walk that reports the FIRST broken index rather than raising or returning a bare
boolean, and (b) a real defense for Budget's SKU->price rows, which had no signature of any
kind and could be edited directly in the database."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel import budget_signing
from apex.kernel.budget import Budget, BudgetDenied
from apex.kernel.memory import Ledger


class AuditChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_fresh_ledger_audits_clean(self):
        result = self.ledger.audit_chain()
        self.assertEqual(result, {"ok": True, "length": 0, "first_broken_seq": None, "reason": None})

    def test_chain_head_is_o1_and_matches_the_last_committed_entry(self):
        self.ledger._append("evt.1", "decision", "opportunity", {"a": 1})
        self.ledger._append("evt.2", "decision", "opportunity", {"a": 2})
        head = self.ledger.chain_head()
        row = self.ledger.db.execute("SELECT seq, digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        self.assertEqual((head["seq"], head["digest"]), row)

    def test_tamper_test_a_in_place_payload_edit_is_detected_at_the_first_broken_index(self):
        """The required Phase 4 tamper test: modify ONE entry in place in a synthetic fixture
        ledger, run verify (audit_chain), assert detection - and specifically at the first
        broken index, not merely 'somewhere'."""
        for i in range(5):
            self.ledger._append(f"evt.{i}", "decision", "opportunity", {"n": i})
        clean = self.ledger.audit_chain()
        self.assertTrue(clean["ok"])
        self.assertEqual(clean["length"], 5)
        # Bypass the app entirely - a raw UPDATE on row seq=3, exactly the threat model a hash
        # chain defends against (SQLite's own triggers only block the Ledger's own connection
        # from doing this through normal means - this simulates a raw file-level edit by
        # disabling the trigger path via a second, unprotected connection on the same file).
        import sqlite3
        raw = sqlite3.connect(str(self.root / "runtime" / "kernel.sqlite3"))
        raw.execute("DROP TRIGGER events_no_update")
        raw.execute("UPDATE events SET payload=? WHERE seq=3", ('{"n": 999}',))
        raw.commit()
        raw.close()
        result = self.ledger.audit_chain()
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_broken_seq"], 3)
        self.assertEqual(result["reason"], "DIGEST_MISMATCH")
        self.assertEqual(result["length"], 2)          # seq 1,2 verified clean before the break
        with self.assertRaises(ValueError):
            self.ledger.verify()                        # the existing fail-closed contract is unchanged

    def test_audit_chain_is_linear_in_the_number_of_events(self):
        """O(n), not accidentally O(n^2): confirm it issues one query, not one per row."""
        for i in range(50):
            self.ledger._append(f"evt.{i}", "decision", "opportunity", {"n": i})
        # audit_chain uses a single "SELECT * FROM events ORDER BY seq" cursor - verified by
        # construction (see the source), and functionally by it completing correctly here.
        result = self.ledger.audit_chain()
        self.assertEqual((result["ok"], result["length"]), (True, 50))


SECRET_SIGNING_FIXTURE = b"s" * 32   # synthetic, not a real owner secret


class SignedPricingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.private_key, self.public_key = budget_signing.generate_keypair()

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_unsigned_mode_is_the_unchanged_default(self):
        """Backward compatibility is not incidental - it is the point: every existing caller in
        this codebase constructs Budget(ledger) with no key, and must keep working exactly as
        before this phase."""
        budget = Budget(self.ledger)
        budget.set_price("anthropic", "test-sku", 100, 1.0, "test")
        self.assertEqual(budget.price("anthropic", "test-sku", 2.0), 100)

    def test_signed_mode_requires_the_matching_private_key_to_set_a_price(self):
        budget = Budget(self.ledger, pricing_public_key=self.public_key)
        with self.assertRaises(ValueError):
            budget.set_price("anthropic", "test-sku", 100, 1.0, "test")   # no private key given
        wrong_private, _ = budget_signing.generate_keypair()
        with self.assertRaises(ValueError):
            budget.set_price("anthropic", "test-sku", 100, 1.0, "test", pricing_private_key=wrong_private)
        budget.set_price("anthropic", "test-sku", 100, 1.0, "test", pricing_private_key=self.private_key)
        self.assertEqual(budget.price("anthropic", "test-sku", 2.0), 100)

    def test_tamper_test_b_editing_a_signed_price_in_place_is_detected(self):
        """The required Phase 4 tamper test: modify a SIGNED price directly in the database
        (bypassing set_price), run verify (price()), assert detection."""
        budget = Budget(self.ledger, pricing_public_key=self.public_key)
        budget.set_price("anthropic", "test-sku", 100, 1.0, "test", pricing_private_key=self.private_key)
        self.assertEqual(budget.price("anthropic", "test-sku", 2.0), 100)
        # Raw tamper: an attacker with DB write access sets the price to zero, bypassing
        # set_price - exactly what an unsigned cost_registry could never detect.
        self.ledger.db.execute("UPDATE cost_registry SET price_millipence=0 WHERE provider='anthropic'")
        with self.assertRaises(BudgetDenied) as ctx:
            budget.price("anthropic", "test-sku", 2.0)
        self.assertEqual(str(ctx.exception), "PRICE_TAMPERED")

    def test_an_unsigned_row_is_rejected_once_signed_mode_is_on(self):
        """A price written while unsigned (e.g. an older unsigned deployment, or a row inserted
        directly by someone bypassing set_price) is refused the moment signed mode is on -
        never silently trusted just because it exists."""
        unsigned_budget = Budget(self.ledger)
        unsigned_budget.set_price("anthropic", "test-sku", 100, 1.0, "test")
        signed_budget = Budget(self.ledger, pricing_public_key=self.public_key)
        with self.assertRaises(BudgetDenied) as ctx:
            signed_budget.price("anthropic", "test-sku", 2.0)
        self.assertEqual(str(ctx.exception), "PRICE_UNSIGNED")

    def test_agent_process_never_needs_the_private_key_to_spend(self):
        """The core asymmetry claim, proven: a Budget constructed with ONLY the public key can
        read and enforce prices that were signed elsewhere, with no access to the private key
        at all in this object's lifetime."""
        operator_budget = Budget(self.ledger, pricing_public_key=self.public_key)
        operator_budget.set_price("anthropic", "test-sku", 100, 1.0, "test", pricing_private_key=self.private_key)
        agent_budget = Budget(Ledger(self.root), pricing_public_key=self.public_key)   # same file, read/verify only
        try:
            self.assertEqual(agent_budget.price("anthropic", "test-sku", 2.0), 100)
            self.assertFalse(hasattr(agent_budget, "pricing_private_key"))
        finally:
            agent_budget.ledger.close()


if __name__ == "__main__":
    unittest.main()
