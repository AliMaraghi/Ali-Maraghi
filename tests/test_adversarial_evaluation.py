"""A-17 Adversarial Evaluation (mission 2026-11-15, Phase 4). Gate P4: the suite must find
at least one real finding or it is too weak. Runs against REAL kernel modules (sandbox,
facts, gateway, approvals) - synthetic data/keys only, nothing persisted to disk beyond a
temp sqlite file this test creates and deletes."""
import secrets
import tempfile
import unittest
from pathlib import Path

from apex.kernel import facts, sandbox
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway
from apex.kernel.memory import Ledger
from apex.roles import adversarial_evaluation as a17


class AdversarialEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self.priv = secrets.token_bytes(32)
        sk = Ed25519PrivateKey.from_private_bytes(self.priv)
        self.pub = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        budget = Budget(self.ledger)
        budget.set_cap("global", "month", 2000)
        for pool in ("core", "intelligence", "studio", "retry"):
            budget.set_cap(pool, "month", 2000)
        self.gateway = ActionGateway(self.ledger, ApprovalBook(self.ledger, secrets.token_bytes(32)), budget)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()
        for t in getattr(self, "_probe_tmps", []):
            t.cleanup()

    def ledger_factory(self):
        """A fresh Ledger per call, each in its own temp dir - P-5/P-6 need clean fact
        tables independent of each other and of self.ledger (used only by the gateway)."""
        probe_tmp = tempfile.TemporaryDirectory()
        self._probe_tmps = getattr(self, "_probe_tmps", []) + [probe_tmp]
        return Ledger(Path(probe_tmp.name))

    def test_suite_runs_all_eight_probes(self):
        results = a17.run_all(sandbox, facts, self.ledger_factory, self.gateway, self.priv, self.pub)
        self.assertEqual(len(results), 8)
        for r in results:
            self.assertIn(r.verdict, ("PASS", "FINDING"))
            self.assertTrue(r.detail)

    def test_p4_is_now_closed_after_the_sandbox_fix(self):
        """P-4 found a real MEDIUM finding (docs/ADVERSARIAL_FINDINGS.md) - sandbox.py's
        FS allowlist was fixed (Phase 5, same day) to use sysconfig's specific stdlib paths
        instead of the overbroad sys.prefix family. Rerunning the same probe now PASSes -
        this is the expected post-fix state, not a weaker gate: the probe still actually
        attempts the same read and would re-report FINDING if the fix regressed."""
        results = a17.run_all(sandbox, facts, self.ledger_factory, self.gateway, self.priv, self.pub)
        by_id = {r.probe_id: r for r in results}
        self.assertEqual(by_id["P-4"].verdict, "PASS", by_id["P-4"].detail)

    def test_all_eight_probes_pass_against_the_patched_kernel(self):
        results = a17.run_all(sandbox, facts, self.ledger_factory, self.gateway, self.priv, self.pub)
        by_id = {r.probe_id: r for r in results}
        for pid in ("P-1", "P-2", "P-3", "P-4", "P-5", "P-6", "P-7", "P-8"):
            self.assertEqual(by_id[pid].verdict, "PASS", f"{pid}: {by_id[pid].detail}")


if __name__ == "__main__":
    unittest.main()
