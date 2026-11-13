"""Offline tests: synthetic proposal -> approval -> mock action -> audit, plus denial paths."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel.approvals import ApprovalBook, ApprovalError, PROPOSAL_TTL, APPROVAL_TTL
from apex.kernel.memory import Ledger
from apex.kernel.policy import KillState, Policy

SECRET = b"s" * 32
OWNER = "owner@example.test"


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.clock = Clock()
        self.book = ApprovalBook(self.ledger, SECRET, clock=self.clock)
        self.policy = Policy(domain="opportunity")

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def propose(self, pid="p1"):
        return self.book.propose(pid, "opportunity", "record_review", "agent:discovery",
                                 {"title": "Synthetic tender"}, ["ev-1"])

    def test_happy_path_is_audited(self):
        self.assertEqual(self.propose(), "PENDING")
        token = self.book.issue("p1", OWNER)
        self.assertEqual(self.book.approve("p1", token, OWNER), "APPROVED")
        self.assertEqual(self.book.execute("p1", self.policy), "EXECUTED")
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity")]
        self.assertEqual(events, ["proposed", "approved", "executed"])
        self.assertEqual(self.ledger.verify(), 3)

    def test_replay_is_rejected(self):
        self.propose()
        token = self.book.issue("p1", OWNER)
        self.book.approve("p1", token, OWNER)
        with self.assertRaisesRegex(ApprovalError, "REPLAY"):
            self.book.approve("p1", token, OWNER)

    def test_payload_tamper_is_rejected(self):
        self.propose()
        token = self.book.issue("p1", OWNER)
        self.ledger.db.execute("UPDATE proposals SET payload=? WHERE id='p1'",
                               ('{"evidence":["ev-1"],"payload":{"title":"Changed"}}',))
        with self.assertRaisesRegex(ApprovalError, "PAYLOAD_TAMPERED"):
            self.book.approve("p1", token, OWNER)
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity")]
        self.assertEqual(events, ["proposed", "tamper"])
        self.assertEqual(self.book.state("p1"), "PENDING")

    def test_forged_signature_is_rejected(self):
        self.propose()
        nonce = self.book.issue("p1", OWNER).split(".")[0]
        with self.assertRaisesRegex(ApprovalError, "BAD_SIGNATURE"):
            self.book.approve("p1", nonce + "." + "0" * 64, OWNER)

    def test_other_identity_cannot_use_token(self):
        self.propose()
        token = self.book.issue("p1", OWNER)
        with self.assertRaisesRegex(ApprovalError, "IDENTITY_MISMATCH"):
            self.book.approve("p1", token, "someone@example.test")

    def test_agent_cannot_approve_itself(self):
        self.propose()
        with self.assertRaisesRegex(ApprovalError, "HUMAN_IDENTITY_REQUIRED"):
            self.book.issue("p1", "agent:discovery")

    def test_token_expires(self):
        self.propose()
        token = self.book.issue("p1", OWNER)
        self.clock.now += APPROVAL_TTL + 1
        with self.assertRaisesRegex(ApprovalError, "TOKEN_EXPIRED"):
            self.book.approve("p1", token, OWNER)

    def test_silence_expires_proposal(self):
        self.propose()
        self.clock.now += PROPOSAL_TTL + 1
        self.assertEqual(self.book.expire_stale(), ["p1"])
        self.assertEqual(self.book.state("p1"), "EXPIRED")
        with self.assertRaisesRegex(ApprovalError, "NOT_PENDING"):
            self.book.issue("p1", OWNER)

    def test_denial_blocks_execution(self):
        self.propose()
        self.assertEqual(self.book.deny("p1", OWNER), "DENIED")
        with self.assertRaisesRegex(ApprovalError, "NOT_APPROVED"):
            self.book.execute("p1", self.policy)

    def test_fourth_daily_proposal_is_deferred(self):
        states = [self.propose(f"p{i}") for i in range(4)]
        self.assertEqual(states, ["PENDING", "PENDING", "PENDING", "DEFERRED"])
        with self.assertRaisesRegex(ApprovalError, "NOT_PENDING"):
            self.book.issue("p3", OWNER)

    def test_kill_switch_blocks_execution_after_approval(self):
        self.propose()
        self.book.approve("p1", self.book.issue("p1", OWNER), OWNER)
        stopped = Policy(domain="opportunity", kill_state=KillState.STOP_EXECUTION)
        with self.assertRaisesRegex(ApprovalError, "STOP_EXECUTION"):
            self.book.execute("p1", stopped)
        self.assertEqual(self.book.state("p1"), "APPROVED")
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity")]
        self.assertEqual(events[-1], "blocked.stop_execution")

    def test_proposal_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            self.book.propose("p9", "opportunity", "record_review", "agent:x", {"a": 1}, [])


if __name__ == "__main__":
    unittest.main()
