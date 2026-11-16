import unittest
import test_missions
from apex.wealth_engine import propose_action, WealthEngineError, DISCLAIMER
from apex.kernel.budget import Budget, BudgetDenied


class WealthEngineTests(unittest.TestCase):
    setUp = test_missions.MissionTests.setUp
    tearDown = test_missions.MissionTests.tearDown

    def fake_pair(self, reply="Action: Move £4,000 into a Stocks & Shares ISA\nReasoning: Unused ISA allowance."):
        def call_anthropic(api_key, system, user_text, max_tokens=150):
            return reply
        return call_anthropic, (lambda: "fake-key")

    def test_empty_portfolio_raises_no_budget_touched(self):
        budget = Budget(self.ledger)
        with self.assertRaises(WealthEngineError):
            propose_action(budget, self.ledger, "   ")

    def test_zero_budget_by_default_blocks_it(self):
        budget = Budget(self.ledger)
        call_anthropic, load_api_key = self.fake_pair()
        with self.assertRaises(BudgetDenied):
            propose_action(budget, self.ledger, "£10,000 in savings", call_anthropic, load_api_key)

    def test_real_parse_and_disclaimer_always_present(self):
        import time
        budget = Budget(self.ledger)
        budget.set_price("anthropic", "wealth-analysis-step", 100, time.time(), "test")
        budget.set_cap("core", "day", 1000)
        call_anthropic, load_api_key = self.fake_pair()
        result = propose_action(budget, self.ledger, "£10,000 in savings, no ISA used this year", call_anthropic, load_api_key)
        self.assertEqual(result["action"], "Move £4,000 into a Stocks & Shares ISA")
        self.assertIn("Unused ISA allowance", result["reasoning"])
        self.assertEqual(result["disclaimer"], DISCLAIMER)

    def test_proposal_recorded_as_claim_not_executed(self):
        import time
        budget = Budget(self.ledger)
        budget.set_price("anthropic", "wealth-analysis-step", 100, time.time(), "test")
        budget.set_cap("core", "day", 1000)
        call_anthropic, load_api_key = self.fake_pair()
        propose_action(budget, self.ledger, "£5,000 savings", call_anthropic, load_api_key)
        rows = self.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='decision' AND event_key LIKE 'wealth-proposal-%'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn('"PROPOSED_NOT_APPROVED"', rows[0][0])

    def test_malformed_reply_shows_raw_text_not_hidden(self):
        import time
        budget = Budget(self.ledger)
        budget.set_price("anthropic", "wealth-analysis-step", 100, time.time(), "test")
        budget.set_cap("core", "day", 1000)
        call_anthropic, load_api_key = self.fake_pair(reply="I'm not sure what to suggest here.")
        result = propose_action(budget, self.ledger, "£1 in savings", call_anthropic, load_api_key)
        self.assertIn("not sure", result["action"])


if __name__ == "__main__":
    unittest.main()
