"""Tests for the agent registry, Decision Twin rules, bitemporal facts, relationship assist, social snapshots and the Gateway adapter bindings."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from apex import agents_registry as reg
from apex import decision_twin, relationship_assist, social_snapshots
from apex.agent_contract import ContractError
from apex.kernel.adapters import build_adapters
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS, GatewayError
from apex.kernel.memory import Ledger
from apex.kernel.temporal import FactStore, TemporalError


def contract(agent_id="8-1", **extra):
    base = {"task_id": "t1", "agent_id": agent_id, "claims": [{"text": "c", "kind": "fact", "evidence_ids": ["e1"]}],
            "risks": [], "unknowns": [], "confidence": 0.8, "evidence": ["e1", "e2"]}
    base.update(extra)
    return base


class RegistryTests(unittest.TestCase):
    def test_eighteen_slots_unresolved_slots_are_disabled(self):
        self.assertEqual({a.slot for a in reg.REGISTRY}, set(reg.SLOTS))
        self.assertEqual(len(reg.SLOTS), 18)
        for slot in ("8-13", "8-14"):
            with self.assertRaisesRegex(reg.IsolationError, "AGENT_UNRESOLVED_SOURCE"):
                reg.get(slot)
        self.assertEqual([a.agent_id for a in reg.REGISTRY if a.slot == "8-11"], ["8-11a", "8-11b", "8-11c", "8-11d", "8-11e"])
        self.assertEqual(len([a for a in reg.REGISTRY if a.slot == "8-12"]), 5)

    def test_isolation_rules(self):
        self.assertTrue(reg.check_inputs("8-1", [reg.PUBLIC, reg.DOSSIER_1]))
        for agent, classes in (("8-1", [reg.DOSSIER_2]), ("8-11a", [reg.FINANCE]), ("8-11c", [reg.MEDICAL]), ("8-15", [reg.EMPLOYER]),
                               ("8-3", [reg.DOSSIER_1]), ("8-12a", [reg.DOSSIER_3]), ("8-8", [reg.DOSSIER_4])):
            with self.assertRaises(reg.IsolationError, msg=f"{agent} {classes}"):
                reg.check_inputs(agent, classes)
        with self.assertRaisesRegex(reg.IsolationError, "CORPORATE_SOURCE_DENIED"):
            reg.check_inputs("8-1", [reg.PUBLIC], data_source="corporate")
        self.assertEqual([a.max_dossier_tier for a in reg.REGISTRY if a.slot in ("8-11", "8-12", "8-15", "8-16", "8-17", "8-18")], [0] * 14)

    def test_output_must_match_contract_and_agent(self):
        self.assertEqual(reg.validate_output("8-1", contract("8-1")).agent_id, "8-1")
        with self.assertRaises(ContractError):
            reg.validate_output("8-1", contract("8-2"))
        with self.assertRaises(ContractError):
            reg.validate_output("8-1", contract("8-1", confidence=2))


class TwinTests(unittest.TestCase):
    def payload(self, **extra):
        base = contract("decision-twin", supporting_patterns=["pattern"], counterfactual="if not, nothing changes", risk_level="low", evidence_count=2)
        base.update(extra)
        return base

    def test_abstain_rules(self):
        self.assertEqual(decision_twin.assess(self.payload()).decision, "PROPOSE")
        cases = ((self.payload(contradictions=["x vs y"]), (), "CONTRADICTIONS_PRESENT"), (self.payload(confidence=0.3), (), "LOW_CONFIDENCE"),
                 (self.payload(evidence_count=1), (), "INSUFFICIENT_EVIDENCE"), (self.payload(), ("financial",), "CONSEQUENTIAL_DOMAIN:financial"),
                 (self.payload(risk_level="high"), (), "HIGH_RISK"), (self.payload(), ("medical", "legal"), "CONSEQUENTIAL_DOMAIN:legal,medical"))
        for payload, domains, reason in cases:
            result = decision_twin.assess(payload, domains)
            self.assertEqual((result.decision, result.abstain_reason, result.human_override_required), ("ABSTAIN", reason, True))

    def test_record_must_be_complete_and_honest(self):
        for bad in (self.payload(evidence_count=5), self.payload(risk_level="extreme"), self.payload(counterfactual=" "), self.payload(supporting_patterns="x")):
            with self.assertRaises(ContractError):
                decision_twin.assess(bad)
        with self.assertRaises(ContractError):
            decision_twin.assess(self.payload(), ("astrology",))

    def test_calibration_caps_autonomy_regardless_of_stated_confidence(self):
        good = [(0.9, True)] * 60
        self.assertAlmostEqual(decision_twin.brier_score(good), 0.01)
        self.assertEqual(decision_twin.earned_autonomy(6, good), 3)
        self.assertEqual(decision_twin.earned_autonomy(2, good), 2)
        self.assertEqual(decision_twin.earned_autonomy(6, [(0.9, True)] * 10), 1)               # too few labelled outcomes
        self.assertEqual(decision_twin.earned_autonomy(6, [(0.99, False)] * 60), 1)             # confidently wrong
        with self.assertRaises(ValueError):
            decision_twin.earned_autonomy(7, good)


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.now = [1000.0]
        self.store = FactStore(self.ledger, clock=lambda: self.now[0])

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_valid_time_history_and_supersession(self):
        london = self.store.assert_fact("personal", "ali", "city", "London", 100.0, ["ev1"])
        self.now[0] = 2000.0
        paris = self.store.assert_fact("personal", "ali", "city", "Paris", 200.0, ["ev2"])
        self.assertEqual(self.store.as_of("personal", "ali", "city", 150.0)["value"], "London")
        self.assertEqual(self.store.as_of("personal", "ali", "city", 250.0)["value"], "Paris")
        self.assertIsNone(self.store.as_of("personal", "ali", "city", 50.0))
        self.assertEqual([h["reason"] for h in self.store.history(london)], ["asserted", "superseded"])
        self.assertEqual(self.store.history(london)[1]["valid_to"], 200.0)
        self.assertEqual(self.store.as_of("personal", "ali", "city", 250.0)["fact_id"], paris)

    def test_corrections_keep_what_was_believed_earlier(self):
        fact = self.store.assert_fact("personal", "ali", "job", "enginer", 100.0, ["ev1"])
        self.now[0] = 5000.0
        self.store.correct(fact, "engineer", ["ev2"])
        self.assertEqual(self.store.as_of("personal", "ali", "job", 150.0)["value"], "engineer")
        self.assertEqual(self.store.as_of("personal", "ali", "job", 150.0, known_at=3000.0)["value"], "enginer")      # belief at that time
        self.assertIsNone(self.store.as_of("personal", "ali", "job", 150.0, known_at=500.0))

    def test_rules_evidence_ordering_domain_and_append_only(self):
        with self.assertRaises(TemporalError):
            self.store.assert_fact("personal", "ali", "x", 1, 10.0, [])
        with self.assertRaises(TemporalError):
            self.store.assert_fact("nowhere", "ali", "x", 1, 10.0, ["e"])
        self.store.assert_fact("personal", "ali", "x", 1, 100.0, ["e"])
        with self.assertRaises(TemporalError):
            self.store.assert_fact("personal", "ali", "x", 2, 100.0, ["e"])                    # must start after the open fact
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("UPDATE fact_versions SET value='x'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("DELETE FROM fact_versions")
        self.assertGreater(self.ledger.verify(), 0)

    def test_end_fact(self):
        fact = self.store.assert_fact("personal", "ali", "role", "a", 100.0, ["e"])
        self.now[0] = 2000.0
        self.store.end_fact(fact, 300.0, ["e2"])
        self.assertEqual(self.store.as_of("personal", "ali", "role", 200.0)["value"], "a")
        self.assertIsNone(self.store.as_of("personal", "ali", "role", 400.0))
        with self.assertRaises(TemporalError):
            self.store.end_fact(fact, 500.0, ["e"])


class SmallModuleTests(unittest.TestCase):
    def test_relationship_assist_refuses_automation_and_never_sends(self):
        for text in ("auto swipe for me", "pretend to be her", "bypass the captcha", "send it for me automatically", "scrape matches"):
            with self.assertRaises(relationship_assist.AssistRefused, msg=text):
                relationship_assist.draft_package("reply", text)
        draft = relationship_assist.draft_package("reply to a friend", "She asked about my weekend", "calm")
        self.assertFalse(draft.send)
        self.assertTrue(draft.requires_owner_review)
        note = relationship_assist.make_note("Sam", "Likes hiking", "2026-11-12")
        self.assertEqual(note.person_label, "Sam")
        with self.assertRaises(ValueError):
            relationship_assist.draft_package("x", "y", tone="aggressive")
        self.assertTrue(relationship_assist.bio_checklist("hi"))

    def test_social_snapshots(self):
        row = social_snapshots.validate_row({"platform": "youtube", "date": "2026-11-12", "source": "api", "account_label": "ch", "metrics": {"views": 10}})
        later = social_snapshots.validate_row({"platform": "youtube", "date": "2026-11-13", "source": "api", "account_label": "ch", "metrics": {"views": 25}})
        self.assertEqual(social_snapshots.daily_delta(row, later), {"views": 15})
        for bad in ({"platform": "myspace"}, {"metrics": {"views": -1}}, {"metrics": {"likes": 1.5}}, {"metrics": {}}, {"date": "12/11/2026"}):
            with self.assertRaises(ValueError):
                social_snapshots.validate_row({"platform": "youtube", "date": "2026-11-12", "source": "api", "metrics": {"views": 1}, **bad})
        with self.assertRaises(ValueError):
            social_snapshots.daily_delta(later, row)


class AdapterBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.book = ApprovalBook(self.ledger, b"k" * 32, clock=lambda: 1_800_000_000.0)
        self.budget = Budget(self.ledger, clock=lambda: 1_800_000_000.0)
        self.budget.set_price("mock", "echo", 0, 0, "synthetic")
        self.sent = []

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def token(self, mode=0o600):
        path = self.root / "gmail.token"
        path.write_text("g" * 40)
        os.chmod(path, mode)
        return str(path)

    def transport(self, method, path, headers, body):
        self.sent.append((method, path))
        return 200, "application/json", json.dumps({"id": "d1", "message": {"id": "m1"}}).encode()

    def run_draft(self, adapters):
        gateway = ActionGateway(self.ledger, self.book, self.budget, adapters=adapters, kinds=dict(DEFAULT_KINDS))
        gateway.submit("d1", "personal", "gmail_draft", "agent:test", {"to": "a@example.test", "subject": "S", "body": "B"}, ["ev"])
        self.book.approve("d1", self.book.issue("d1", "owner@example.test"), "owner@example.test")
        return gateway.execute("d1")

    def test_unconfigured_adapters_return_not_configured(self):
        for paths in ({}, {"gmail": str(self.root / "missing")}, {"gmail": self.token(0o644)}):
            adapters = build_adapters(paths, {"gmail": self.transport})
            self.assertFalse(adapters["gmail"].configured())
        self.assertFalse(build_adapters({"gmail": self.token()}, {})["gmail"].configured())            # token but no transport
        with self.assertRaisesRegex(GatewayError, "NOT_CONFIGURED"):
            self.run_draft(build_adapters({}, {}))
        self.assertEqual(self.sent, [])

    def test_configured_gmail_adapter_only_creates_drafts_through_the_gateway(self):
        adapters = build_adapters({"gmail": self.token()}, {"gmail": self.transport})
        self.assertTrue(adapters["gmail"].configured())
        self.assertEqual(self.run_draft(adapters), "EXECUTED")
        self.assertEqual(self.sent, [("POST", "/gmail/v1/users/me/drafts")])


if __name__ == "__main__":
    unittest.main()
