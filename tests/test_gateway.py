"""Action Gateway: typed payloads, approval gate, policy, budget, mock adapters, audit. Synthetic only."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS, GatewayError, KindSpec, MockAdapter, UnconfiguredAdapter
from apex.kernel.memory import Ledger
from apex.kernel.policy import KillState

OWNER = "owner@example.test"
T0 = 1_800_000_000.0


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.book = ApprovalBook(self.ledger, b"k" * 32, clock=lambda: T0)
        self.budget = Budget(self.ledger, clock=lambda: T0)
        self.budget.set_price("mock", "echo", 0, 0, "synthetic mock provider")
        self.budget.set_price("acme", "unit", 10_000, T0 - 5, "https://example.test/price")      # 10p / unit
        self.mock = MockAdapter()
        kinds = dict(DEFAULT_KINDS)
        kinds["paid_mock"] = KindSpec(frozenset({"studio"}), {"units": int}, adapter="mock", pool="studio",
                                      provider="acme", sku="unit", units_field="units")
        kinds["external_send"] = KindSpec(frozenset({"personal"}), {"text": str}, adapter="email")
        self.gw = ActionGateway(self.ledger, self.book, self.budget,
                                adapters={"mock": self.mock, "email": UnconfiguredAdapter("email")}, kinds=kinds)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def approve(self, pid):
        self.book.approve(pid, self.book.issue(pid, OWNER), OWNER)

    def submit(self, pid, kind, domain, payload):
        return self.gw.submit(pid, domain, kind, "agent:test", payload, ["ev-1"])

    def events(self, domain):
        return [r["payload"]["event"] for r in self.ledger.records(domain)]

    def test_local_record_end_to_end(self):
        self.submit("a1", "record_decision", "opportunity", {"note": "synthetic"})
        with self.assertRaisesRegex(GatewayError, "NOT_APPROVED"):
            self.gw.execute("a1")
        self.approve("a1")
        self.assertEqual(self.gw.execute("a1"), "EXECUTED")
        self.assertEqual(self.events("opportunity"), ["proposed", "approved", "executed", "dispatched"])
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM budget_reservations").fetchone()[0], 0)

    def test_typed_payload_rules(self):
        for payload, code in [({"note": "x", "shell": "rm -rf /"}, "PAYLOAD_FIELDS_MISMATCH"),
                              ({"note": 5}, "PAYLOAD_TYPE_MISMATCH"), ({"note": ""}, "PAYLOAD_TEXT_BOUNDS"),
                              ({"note": "x" * 2001}, "PAYLOAD_TEXT_BOUNDS")]:
            with self.assertRaisesRegex(GatewayError, code):
                self.submit("t1", "record_decision", "opportunity", payload)
        with self.assertRaisesRegex(GatewayError, "UNKNOWN_ACTION_KIND"):
            self.submit("t2", "run_shell", "opportunity", {"note": "x"})
        with self.assertRaisesRegex(GatewayError, "DOMAIN_DENIED"):
            self.submit("t3", "paid_mock", "personal", {"units": 1})
        with self.assertRaisesRegex(GatewayError, "PRIVATE_DATA_UNSUPPORTED"):
            self.gw.submit("t4", "opportunity", "record_decision", "agent:test", {"note": "x"}, ["ev"], sensitivity="private")

    def test_mock_adapter_zero_cost_dispatch_is_recorded(self):
        self.submit("m1", "mock_notify", "studio", {"message": "hello"})
        self.approve("m1")
        self.gw.execute("m1")
        self.assertEqual(self.mock.sent, [("exec.m1", {"message": "hello"})])
        self.assertEqual(self.ledger.db.execute("SELECT state,reserved_minor FROM budget_reservations").fetchone(), ("SETTLED", 0))

    def test_paid_action_blocked_by_default_then_reserved_and_settled(self):
        self.submit("p1", "paid_mock", "studio", {"units": 3})
        self.approve("p1")
        with self.assertRaisesRegex(GatewayError, "BUDGET_NO_CAP_CONFIGURED"):
            self.gw.execute("p1")
        self.assertEqual(self.mock.sent, [])
        self.assertEqual(self.book.state("p1"), "APPROVED")
        self.budget.set_cap("studio", "day", 100)
        self.mock.actual_units = 2                                         # actual use lower than estimate
        self.gw.execute("p1")
        self.assertEqual(self.ledger.db.execute("SELECT state,reserved_minor,actual_minor FROM budget_reservations").fetchone(),
                         ("SETTLED", 30, 20))
        self.assertEqual(self.book.state("p1"), "EXECUTED")

    def test_failed_dispatch_releases_and_retry_uses_retry_pool(self):
        self.budget.set_cap("studio", "day", 100)
        self.mock.fail_times = 1
        self.submit("f1", "paid_mock", "studio", {"units": 3})
        self.approve("f1")
        with self.assertRaisesRegex(GatewayError, "DISPATCH_FAILED"):
            self.gw.execute("f1")
        self.assertEqual(self.ledger.db.execute("SELECT state FROM budget_reservations WHERE key='exec.f1'").fetchone()[0], "RELEASED")
        with self.assertRaisesRegex(GatewayError, "BUDGET_NO_CAP_CONFIGURED"):
            self.gw.execute("f1")                                           # retry pool has no cap yet
        self.budget.set_cap("retry", "day", 100)
        self.gw.execute("f1")
        self.assertEqual(self.ledger.db.execute("SELECT pool,state FROM budget_reservations WHERE key='exec.f1.r1'").fetchone(),
                         ("retry", "SETTLED"))

    def test_unconfigured_external_adapter_is_not_simulated(self):
        self.submit("e1", "external_send", "personal", {"text": "hi"})
        self.approve("e1")
        with self.assertRaisesRegex(GatewayError, "NOT_CONFIGURED"):
            self.gw.execute("e1")
        self.assertEqual(self.book.state("e1"), "APPROVED")
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM budget_reservations").fetchone()[0], 0)
        self.assertIn("refused.not_configured", self.events("personal"))

    def test_kill_state_and_durable_stop_block_before_any_reservation(self):
        self.budget.set_cap("studio", "day", 100)
        self.submit("k1", "paid_mock", "studio", {"units": 1})
        self.approve("k1")
        self.gw.kill_state = KillState.STOP_EXECUTION
        with self.assertRaisesRegex(GatewayError, "STOP_EXECUTION"):
            self.gw.execute("k1")
        self.gw.kill_state = KillState.RUNNING
        self.ledger.db.execute("CREATE TABLE IF NOT EXISTS job_meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, stop TEXT NOT NULL)")
        self.ledger.db.execute("INSERT OR REPLACE INTO job_meta VALUES (1,1,'FREEZE_INGRESS')")
        with self.assertRaisesRegex(GatewayError, "DURABLE_STOP_ACTIVE"):
            self.gw.execute("k1")
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM budget_reservations").fetchone()[0], 0)
        self.assertEqual(self.mock.sent, [])

    def test_no_second_execution_and_chain_stays_valid(self):
        self.submit("d1", "mock_notify", "studio", {"message": "once"})
        self.approve("d1")
        self.gw.execute("d1")
        with self.assertRaisesRegex(GatewayError, "NOT_APPROVED"):
            self.gw.execute("d1")
        self.assertEqual(len(self.mock.sent), 1)
        self.assertGreater(self.ledger.verify(), 0)


if __name__ == "__main__":
    unittest.main()
