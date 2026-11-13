"""Dating message assistant: pure text-in/LLM-out, budget-gated, no network/browser/storage."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "core"))

import dating_agent  # noqa: E402
from apex.kernel.budget import Budget, BudgetDenied  # noqa: E402
from apex.kernel.memory import Ledger  # noqa: E402


class DatingAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_empty_profile_is_rejected_before_any_spend(self):
        with self.assertRaises(ValueError):
            dating_agent.generate_openers(self.budget, "   ")
        self.assertEqual(self.budget.spent("core", "day", time.time()), 0)

    def test_zero_budget_by_default_blocks_generation(self):
        with self.assertRaises(BudgetDenied):
            dating_agent.generate_openers(self.budget, "Loves hiking and dogs.")

    def test_generates_and_settles_budget(self):
        self.budget.set_price("anthropic", "dating-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch.object(dating_agent, "load_api_key", return_value="fake-key"), \
             mock.patch.object(dating_agent, "call_anthropic", return_value="1. Hi!\n2. Hey!\n3. Hello!"):
            result = dating_agent.generate_openers(self.budget, "Loves hiking and dogs.")
        self.assertIn("Hi!", result)
        self.assertGreater(self.budget.spent("core", "day", time.time()), 0)

    def test_nothing_is_persisted_to_the_ledger(self):
        # The pasted profile text / generated openers must never land in a Ledger table - this
        # agent is stateless by design (no third-party dossier).
        tables_before = {r[0] for r in self.ledger.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.budget.set_price("anthropic", "dating-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch.object(dating_agent, "load_api_key", return_value="fake-key"), \
             mock.patch.object(dating_agent, "call_anthropic", return_value="1. Hi!"):
            dating_agent.generate_openers(self.budget, "Loves hiking.")
        tables_after = {r[0] for r in self.ledger.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables_before, tables_after)


if __name__ == "__main__":
    unittest.main()
