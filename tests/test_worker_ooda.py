"""Budget cap wiring, the notepad demo queue path, the LaptopBrowserAdapter and the OODA act-on-approved step. No network, no laptop."""
import importlib.util
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from apex.bridge_auth import create_key
from apex.bridge_queue import BridgeQueue, DEMO_TEXT, QueueError
from apex.kernel.adapters import LaptopBrowserAdapter
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget, BudgetDenied
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS, GatewayError
from apex.kernel.memory import Ledger

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("laptop_agent", ROOT / "scripts" / "laptop_agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class DemoQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.q = BridgeQueue(self.ledger, clock=lambda: 1_800_000_000.0)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_default_text_and_leased_shape(self):
        task_id = self.q.enqueue_notepad_demo()
        leased = self.q.lease_next()
        self.assertEqual((leased["id"], leased["kind"], leased["steps"]), (task_id, "notepad_demo", {"text": DEMO_TEXT}))
        self.assertIsNone(leased["url"])
        self.assertTrue(agent.task_ok(leased))

    def test_text_is_bounded_and_plain(self):
        for bad in ("", "x" * 61, "has\nnewline", "<script>alert(1)</script>", "rm -rf /; echo"):
            with self.assertRaises(QueueError, msg=bad):
                self.q.enqueue_notepad_demo(bad)
        self.q.enqueue_notepad_demo("Apex is Alive, v2!")       # within the allowed character set

    def test_agent_rejects_a_tampered_demo_task(self):
        leased = {"id": "x", "purpose": "p", "url": None, "kind": "notepad_demo", "steps": {"text": "ok", "extra": 1}}
        self.assertFalse(agent.task_ok(leased))
        leased["steps"] = {"text": "shell; rm -rf"}
        self.assertFalse(agent.task_ok(leased))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_unconfigured_until_a_bridge_key_exists(self):
        a = LaptopBrowserAdapter(self.ledger, self.root)
        self.assertFalse(a.configured())
        create_key(self.root)
        self.assertTrue(a.configured())

    def test_dispatch_only_enqueues_never_runs_anything(self):
        create_key(self.root)
        a = LaptopBrowserAdapter(self.ledger, self.root)
        a.dispatch({"purpose": "open it", "url": "https://console.cloud.google.com/", "steps_json": "[]"}, "k1")
        self.assertEqual(BridgeQueue(self.ledger).summary()["counts"], {"PENDING": 1})


class ApprovedActGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.now = [1_800_000_000.0]
        self.book = ApprovalBook(self.ledger, b"k" * 32, clock=lambda: self.now[0])
        self.budget = Budget(self.ledger, clock=lambda: self.now[0])
        self.budget.set_price("mock", "echo", 0, 0, "synthetic")
        create_key(self.root)
        kinds = dict(DEFAULT_KINDS)
        from apex.kernel.gateway import KindSpec
        kinds["laptop_browser_task"] = KindSpec(frozenset({"personal"}), {"purpose": str, "url": str, "steps_json": str}, adapter="laptop_browser")
        self.gateway = ActionGateway(self.ledger, self.book, self.budget, adapters={"laptop_browser": LaptopBrowserAdapter(self.ledger, self.root)}, kinds=kinds)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_pending_proposal_is_not_acted_on(self):
        import worker_loop
        self.gateway.submit("t1", "personal", "laptop_browser_task", "agent:A-5",
                            {"purpose": "open it", "url": "https://console.cloud.google.com/", "steps_json": "[]"}, ["ev"])
        self.assertEqual(worker_loop.act_on_approved(self.gateway, self.book), [])
        self.assertEqual(BridgeQueue(self.ledger).summary()["counts"], {})

    def test_approved_proposal_is_executed_exactly_once(self):
        import worker_loop
        self.gateway.submit("t1", "personal", "laptop_browser_task", "agent:A-5",
                            {"purpose": "open it", "url": "https://console.cloud.google.com/", "steps_json": "[]"}, ["ev"])
        self.book.approve("t1", self.book.issue("t1", "owner@example.test"), "owner@example.test")
        acted = worker_loop.act_on_approved(self.gateway, self.book)
        self.assertEqual([a["id"] for a in acted], ["t1"])
        self.assertEqual(BridgeQueue(self.ledger).summary()["counts"], {"PENDING": 1})
        self.assertEqual(worker_loop.act_on_approved(self.gateway, self.book), [])   # already EXECUTED: not acted on again


class BudgetCapWiringTests(unittest.TestCase):
    def test_monthly_cap_blocks_over_spend_but_not_free_mock_calls(self):
        import agents_runner as runner
        tmp = tempfile.TemporaryDirectory()
        try:
            ledger = Ledger(Path(tmp.name))
            budget = Budget(ledger)
            budget.set_price("mock", "echo", 0, 0, "synthetic")
            budget.set_price("vendor", "unit", 50_000, 0, "synthetic 50p/unit")  # millipence: 50_000/1000 = 50 pence per unit
            budget.set_cap("global", "month", runner.MONTHLY_BUDGET_PENCE)
            for pool in ("core", "intelligence", "studio", "retry"):
                budget.set_cap(pool, "month", runner.MONTHLY_BUDGET_PENCE)
            budget.reserve("free1", "core", "mock", "echo", 1000)                        # free local calls still work
            budget.reserve("paid1", "studio", "vendor", "unit", 40)                      # 2000p, exactly at the cap
            with self.assertRaises(BudgetDenied):
                budget.reserve("paid2", "studio", "vendor", "unit", 1)                   # one more unit exceeds GBP 20/month
            ledger.close()
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()


class AutoConfirmFlagTests(unittest.TestCase):
    """The laptop-side second prompt is opt-in and laptop-only; hard safety rails are never affected by it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flag = Path(self.tmp.name) / "auto_confirm"
        agent.AUTO_CONFIRM_FILE = self.flag

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_to_asking_and_only_the_owner_can_enable_it(self):
        self.assertFalse(self.flag.exists())
        self.assertFalse(agent.auto_confirm_enabled())
        self.flag.write_text("")
        self.assertTrue(agent.auto_confirm_enabled())
        self.flag.unlink()
        self.assertFalse(agent.auto_confirm_enabled())

    def test_declined_demo_task_without_the_flag_never_runs(self):
        task = {"purpose": "p", "url": None, "kind": "notepad_demo", "steps": {"text": "x"}}
        console = unittest.mock.Mock()
        console.ask.return_value = "n"
        result = agent.handle(task, console)
        self.assertEqual(result["status"], "DECLINED_BY_OWNER")

    def test_host_allowlist_still_applies_with_auto_confirm_on(self):
        self.flag.write_text("")
        self.assertFalse(agent.host_ok("https://linkedin.com/jobs"))
        self.assertFalse(agent.host_ok("http://console.cloud.google.com/"))

    def test_consent_and_secret_detection_still_apply_with_auto_confirm_on(self):
        self.flag.write_text("")
        self.assertTrue(agent.CONSENT_WORDS.search("Allow") and agent.CONSENT_WORDS.search("Sign in"))
        self.assertTrue(agent.SECRET_FIELD.search("input[name=password]"))



if __name__ == "__main__":
    unittest.main()
