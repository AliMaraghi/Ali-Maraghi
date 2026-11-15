"""Phase 2 driver model (brutal-honesty directive, 2026-11-15). All synthetic fixtures. Proves:
a manifest-based registration protocol with a real permission check, hot-swap (install/enable/
run/disable/remove) with zero edits to agents_impl.py/agents_governing.py/DEFAULT_KINDS, and
that one real existing role (A-10 Social & Relational) can run hosted under this model with
zero kernel edits - the required migration proof, without migrating the rest of the roster."""
import tempfile
import unittest
from pathlib import Path

from apex.agents_impl import SocialRelational
from apex.agents_runtime import AgentContext
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.drivers import DriverInstallError, DriverManifest, DriverRegistry
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS, KindSpec
from apex.kernel.memory import Ledger

SECRET = b"k" * 32


class DriverLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.book = ApprovalBook(self.ledger, SECRET, clock=lambda: 1_800_000_000.0)
        self.gateway = ActionGateway(self.ledger, self.book, Budget(self.ledger))
        self.registry = DriverRegistry(self.gateway)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_install_requesting_an_unregistered_kind_fails_before_ever_running(self):
        manifest = DriverManifest("synthetic-1", "Synthetic Driver", "demo",
                                  frozenset({"a_kind_nobody_registered"}), frozenset(), lambda ctx, p: None)
        with self.assertRaises(DriverInstallError) as ctx:
            self.registry.install(manifest)
        self.assertIn("UNKNOWN_KIND", str(ctx.exception))
        self.assertEqual(self.registry.list(), [])

    def test_full_hotswap_lifecycle_install_enable_run_disable_remove(self):
        """The literal gate: a synthetic new role installs, enables, runs, disables and is
        removed with zero edits outside its own driver definition."""
        calls = []
        manifest = DriverManifest("synthetic-1", "Synthetic Driver", "a demo capability",
                                  frozenset({"record_decision"}), frozenset({"public"}),
                                  lambda ctx, payload: calls.append(payload))
        self.registry.install(manifest)
        self.assertEqual(self.registry.list(), [{"driver_id": "synthetic-1", "name": "Synthetic Driver",
                                                  "provides": "a demo capability", "enabled": False}])
        with self.assertRaises(DriverInstallError):
            self.registry.run("synthetic-1", None, {})          # not enabled yet
        self.registry.enable("synthetic-1")
        self.registry.run("synthetic-1", None, {"note": "hello"})
        self.assertEqual(calls, [{"note": "hello"}])
        self.registry.disable("synthetic-1")
        with self.assertRaises(DriverInstallError):
            self.registry.run("synthetic-1", None, {})          # disabled again
        self.registry.remove("synthetic-1")
        self.assertEqual(self.registry.list(), [])
        with self.assertRaises(DriverInstallError):
            self.registry.run("synthetic-1", None, {})          # gone

    def test_cannot_install_the_same_driver_id_twice(self):
        manifest = DriverManifest("dup", "D", "x", frozenset(), frozenset(), lambda ctx, p: None)
        self.registry.install(manifest)
        with self.assertRaises(DriverInstallError):
            self.registry.install(manifest)

    def test_a_driver_requesting_a_pinned_money_kind_still_goes_through_the_real_gateway(self):
        """The permission check approves the REQUEST (the kind exists); it is not a bypass of
        approval. Running this driver still only produces a PENDING proposal - no auto-approval
        path exists anywhere in this model."""
        def propose_money_action(ctx, payload):
            return self.gateway.submit("driver-money-1", "personal", "finance_action_proposal",
                                       "agent:synthetic-driver",
                                       {"action_name": "exercise_espp_now", "scenario_text": "synthetic test scenario",
                                        "gain_pence": 100, "tax_pence": 10, "net_pence_clamped": 90,
                                        "evaluator_verdict": "{}", "fact_id": 0},
                                       ["fact:1"])
        manifest = DriverManifest("money-driver", "Money Driver", "demo",
                                  frozenset({"finance_action_proposal"}), frozenset({"personal"}), propose_money_action)
        self.registry.install(manifest)
        self.registry.enable("money-driver")
        state = self.registry.run("money-driver", None, {})
        self.assertEqual(state, "PENDING")
        self.assertEqual(self.book.view("driver-money-1")["state"], "PENDING")

    def test_installing_a_driver_touches_no_kernel_file(self):
        """Not a runtime assertion (that would be checking git diff mid-test, which is not
        meaningful here) but a structural one: DriverRegistry.install() never imports or
        references agents_impl, agents_governing, or DEFAULT_KINDS as a mutable target - it
        only reads self.gateway.kinds, which is the Gateway's OWN existing registry."""
        import ast
        import inspect
        from apex.kernel import drivers
        tree = ast.parse(inspect.getsource(drivers))
        tree.body = tree.body[1:] if isinstance(tree.body[0], ast.Expr) else tree.body   # drop module docstring
        code_only = ast.unparse(tree)
        self.assertNotIn("agents_impl", code_only)
        self.assertNotIn("agents_governing", code_only)
        self.assertNotIn("DEFAULT_KINDS", code_only)


class MigrateOneExistingRoleTests(unittest.TestCase):
    """The required Phase 2(d) proof: ONE existing, already-real role (A-10 Social &
    Relational) runs hosted under the driver model, with zero edits to agents_impl.py,
    agents_governing.py or DEFAULT_KINDS. Only this one role - the rest of the 18-role roster
    stays exactly as it is; this is a capability proof, not a migration of the whole system."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "inbox").mkdir()
        self.ledger = Ledger(self.root)
        self.book = ApprovalBook(self.ledger, SECRET, clock=lambda: 1_800_000_000.0)
        self.gateway = ActionGateway(self.ledger, self.book, Budget(self.ledger))
        self.registry = DriverRegistry(self.gateway)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_a10_social_relational_runs_hosted_as_a_driver_with_identical_output(self):
        (self.root / "inbox" / "relationship_requests.json").write_text(
            '{"notes": [{"person_label": "A", "text": "met at a meetup", "created": "2027-01-10"}]}')

        def run_a10_as_a_driver(ctx, payload):
            agent_ctx = AgentContext(now=payload["now"], today=payload["today"],
                                     inbox=Path(payload["inbox"]), rules=Path(payload["rules"]))
            return SocialRelational().run(agent_ctx).contract      # the SAME unmodified A-10 class

        manifest = DriverManifest("a10-social-relational", "Social & Relational (driver-hosted)",
                                  "owner-reviewed relationship notes/drafts/bio checklists",
                                  frozenset(), frozenset({"public"}), run_a10_as_a_driver)
        self.registry.install(manifest)
        self.registry.enable("a10-social-relational")
        driver_contract = self.registry.run("a10-social-relational", None,
                                             {"now": 1_800_000_000.0, "today": "2027-01-15",
                                              "inbox": str(self.root / "inbox"), "rules": str(self.root / "inbox")})

        direct_ctx = AgentContext(now=1_800_000_000.0, today="2027-01-15",
                                  inbox=self.root / "inbox", rules=self.root / "inbox")
        direct_contract = SocialRelational().run(direct_ctx).contract
        self.assertEqual(driver_contract, direct_contract)
        self.assertTrue(any("Note recorded for 'A'" in c["text"] for c in driver_contract["claims"]))


if __name__ == "__main__":
    unittest.main()
