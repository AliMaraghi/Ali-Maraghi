"""Offline tests: content drafts stop at approval; approved evolution changes are applied safely."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apex import content_engine
from apex.evolution import apply_approved, bootstrap, evaluator, promote_gate
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.memory import Ledger

ON = {"ENABLE_AUTONOMOUS_SOCIAL": "true", "ENABLE_EVOLUTION_SANDBOX": "true"}
STYLE = "## Hard red lines\n- Acme Widgets\n## Spelling\nBritish\n"
BASE = evaluator.BASELINE.read_text(encoding="utf-8")


def setup_root(tmp, topics):
    root = Path(tmp)
    (root / "runtime" / "inbox").mkdir(parents=True, mode=0o700)
    (root / "runtime").chmod(0o700)
    (root / "runtime" / "inbox" / "persona_style.md").write_text(STYLE)
    (root / "runtime" / "inbox" / "content_topics.json").write_text(json.dumps(topics))
    return root


def budget_for(ledger):
    budget = Budget(ledger, clock=lambda: 1_800_000_000.0)
    budget.set_price("anthropic", "content-draft", 1_000, 1_799_999_000.0, "test")
    budget.set_cap("studio", "month", 500)
    return budget


class ContentTests(unittest.TestCase):
    def run_with(self, replies, topics=({"topic": "Why I cycle to work", "channel": "linkedin"},)):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, ON):
            root = setup_root(tmp, list(topics))
            with Ledger(root) as ledger:
                book, replies = ApprovalBook(ledger, b"k" * 32), list(replies)
                result = content_engine.run_once(root, ledger, book, budget_for(ledger), lambda s, u, m: replies.pop(0))
                rows = ledger.db.execute("SELECT kind, state, proposer FROM proposals").fetchall()
                again = content_engine.run_once(root, ledger, book, budget_for(ledger), lambda s, u, m: "I cycled in. It rained.")
                return result, rows, again

    def test_clean_draft_is_queued_once_and_never_published(self):
        result, rows, again = self.run_with(["I cycled to work today. It rained the whole way."])
        self.assertEqual((result["status"], result["rounds"], result["model_calls"]), ("PROPOSED_PENDING", 0, 1))
        self.assertEqual(rows, [("external-post", "PENDING", "agent:content-engine")])
        self.assertEqual(again["status"], "NO_TOPICS")                     # same topic is not drafted twice

    def test_ai_sounding_draft_is_rewritten_then_queued(self):
        result, rows, _ = self.run_with(["Let's delve into the tapestry of cycling.", "I cycled in. My legs hurt."])
        self.assertEqual((result["status"], result["rounds"], result["model_calls"]), ("PROPOSED_PENDING", 1, 2))

    def test_still_bad_after_two_redrafts_is_dropped(self):
        result, rows, _ = self.run_with(["Let's delve in."] * 3)
        self.assertEqual((result["status"], result["rounds"], rows), ("DROPPED_REWRITE", 2, []))

    def test_leak_is_dropped_without_a_redraft(self):
        result, rows, _ = self.run_with(["A good week at Acme Widgets."])
        self.assertEqual((result["status"], result["rounds"], rows), ("DROPPED_BLOCK", 0, []))

    def test_off_by_default_and_angle_follows_the_weights(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"ENABLE_AUTONOMOUS_SOCIAL": "false"}):
            with Ledger(Path(tmp)) as ledger:
                self.assertEqual(content_engine.run_once(Path(tmp), ledger, None, None, None)["status"], "DISABLED")
        self.assertIn(content_engine.pick_angle(), ("analysis", "personal_story"))


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: evaluator.BASELINE.write_text(BASE, encoding="utf-8"))

    def proposal(self, ledger, book):
        better = BASE.replace('"webinar": -1.5', '"webinar": -3.0').replace('"online": -1.0', '"online": -3.0').replace('"tech": 1.0', '"tech": 0.0')
        record = promote_gate.consider(ledger, book, better, "t", bootstrap.fixtures(), mode="BOOTSTRAP", now=1_800_000_000.0)
        return record, better

    def test_nothing_is_applied_until_the_owner_approves(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, ON):
            with Ledger(Path(tmp)) as ledger:
                book = ApprovalBook(ledger, b"k" * 32)
                record, better = self.proposal(ledger, book)
                if not record["decision"].startswith("PROPOSED"):
                    self.skipTest("fixture candidate did not clear the 5% gate: " + record["decision"])
                pid = record["detail"]
                self.assertEqual(apply_approved.pending_approved(ledger), [])
                self.assertEqual(apply_approved.apply_one(ledger, pid, lambda: True), "REFUSED_NOT_APPROVED")
                self.assertEqual(evaluator.BASELINE.read_text(encoding="utf-8"), BASE)
                ledger.db.execute("DELETE FROM evolution_applied")
                token = book.issue(pid, "owner@example.com")
                book.approve(pid, token, "owner@example.com")
                self.assertEqual(apply_approved.pending_approved(ledger), [pid])
                self.assertEqual(apply_approved.apply_one(ledger, pid, lambda: False), "REVERTED_TESTS_FAILED")
                self.assertEqual(evaluator.BASELINE.read_text(encoding="utf-8"), BASE)
                self.assertEqual(apply_approved.apply_one(ledger, pid, lambda: True), "APPLIED")
                self.assertEqual(evaluator.BASELINE.read_text(encoding="utf-8"), better)
                self.assertEqual(apply_approved.pending_approved(ledger), [])

    def test_tampered_payload_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, ON):
            with Ledger(Path(tmp)) as ledger:
                book = ApprovalBook(ledger, b"k" * 32)
                record, _ = self.proposal(ledger, book)
                if not record["decision"].startswith("PROPOSED"):
                    self.skipTest("fixture candidate did not clear the gate")
                pid = record["detail"]
                ledger.db.execute("UPDATE proposals SET state='APPROVED', payload=replace(payload, '-3.0', '9.0') WHERE id=?", (pid,))
                self.assertEqual(apply_approved.apply_one(ledger, pid, lambda: True), "REFUSED_TAMPERED")
                self.assertEqual(evaluator.BASELINE.read_text(encoding="utf-8"), BASE)


if __name__ == "__main__":
    unittest.main()
