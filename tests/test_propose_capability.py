"""scripts/propose_capability.py: draft-only, human-gated capability proposals.

Recommendation #3 from the second brutal-honesty self-audit, bounded by AGENTS.md's controlled-
evolution doctrine: this must PROPOSE a draft, never test/deploy/adopt it. These tests check that
boundary as much as the happy path.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "core"))

import propose_capability  # noqa: E402
from apex.kernel import facts  # noqa: E402
from apex.kernel.approvals import ApprovalBook  # noqa: E402
from apex.kernel.budget import Budget, BudgetDenied  # noqa: E402
from apex.kernel.gateway import ActionGateway, DEFAULT_KINDS  # noqa: E402
from apex.kernel.memory import Ledger  # noqa: E402

SECRET = b"x" * 32
DRAFT_REPLY = (
    "NAME: weather_brief\n"
    "NOTES: Reads an owner-supplied forecast file and summarises tomorrow's weather.\n"
    "CODE:\n"
    "def weather_brief(data):\n"
    "    return data.get('forecast', 'NOT_MODELLED')\n")


class ProposeCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)
        self.budget.set_price("anthropic", "capability-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 10000)
        self.book = ApprovalBook(self.ledger, SECRET)
        self.gateway = ActionGateway(self.ledger, self.book, self.budget,
                                      kinds={**DEFAULT_KINDS, "capability_proposal": propose_capability.CAPABILITY_PROPOSAL_KIND})

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_draft_parses_name_notes_and_code(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=DRAFT_REPLY):
            draft = propose_capability.draft_capability(self.budget, "tell me tomorrow's weather")
        self.assertEqual(draft["capability_name"], "weather_brief")
        self.assertIn("Reads an owner-supplied forecast file", draft["draft_notes"])
        self.assertIn("def weather_brief", draft["draft_code"])

    def test_malformed_reply_still_returns_something_safe(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="total garbage, no format"):
            draft = propose_capability.draft_capability(self.budget, "something unparseable")
        self.assertEqual(draft["capability_name"], "UNNAMED")
        self.assertEqual(draft["draft_code"], "")

    def test_propose_logs_a_fact_and_submits_a_pending_proposal(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=DRAFT_REPLY):
            result = propose_capability.propose(self.ledger, self.gateway, self.budget, "tell me tomorrow's weather")
        self.assertEqual(result["state"], "PENDING")
        gap = facts.query_fact(self.ledger, "owner", "capability_gap")
        self.assertEqual(gap["object"], "tell me tomorrow's weather")
        view = self.book.view(result["proposal_id"])
        self.assertEqual(view["state"], "PENDING")
        self.assertEqual(view["kind"], "capability_proposal")
        self.assertEqual(view["payload"]["capability_name"], "weather_brief")

    def test_repeated_identical_request_is_a_duplicate_not_a_second_proposal(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=DRAFT_REPLY):
            first = propose_capability.propose(self.ledger, self.gateway, self.budget, "tell me tomorrow's weather")
            with self.assertRaises(Exception):
                propose_capability.propose(self.ledger, self.gateway, self.budget, "tell me tomorrow's weather")
        # The gap was still logged twice (facts are append-only, never deduped away).
        history = facts.fact_history(self.ledger, "owner", "capability_gap")
        self.assertEqual(len(history), 2)
        self.assertEqual(first["state"], "PENDING")

    def test_budget_denial_raises_and_spends_nothing(self):
        import unittest.mock as mock
        unpriced = Budget(Ledger(Path(tempfile.mkdtemp())))
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=DRAFT_REPLY):
            with self.assertRaises(BudgetDenied):
                propose_capability.propose(self.ledger, self.gateway, unpriced, "tell me tomorrow's weather")

    def test_sandbox_result_is_attached_to_the_payload_and_pass_for_benign_code(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=DRAFT_REPLY):
            result = propose_capability.propose(self.ledger, self.gateway, self.budget, "tell me tomorrow's weather")
        self.assertEqual(result["sandbox_result"], "PASS")
        view = self.book.view(result["proposal_id"])
        self.assertEqual(view["payload"]["sandbox_result"], "PASS")
        self.assertIn("Sandbox check", view["model_commentary"])

    def test_draft_that_tries_the_network_is_flagged_crashed_not_hidden(self):
        import unittest.mock as mock
        network_draft = ("NAME: exfil\nNOTES: tries to reach the network\nCODE:\n"
                          "import socket\ns = socket.socket()\ns.connect(('8.8.8.8', 53))\n")
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=network_draft):
            result = propose_capability.propose(self.ledger, self.gateway, self.budget, "reach the internet for me")
        self.assertTrue(result["sandbox_result"].startswith("CRASHED:"))
        self.assertIn("SANDBOX_NETWORK_DENIED", result["sandbox_result"])
        # Still PENDING - a failed sandbox check is visible to the reviewer, it never silently blocks the proposal
        self.assertEqual(result["state"], "PENDING")

    def test_draft_that_reads_a_real_file_is_flagged_crashed_not_hidden(self):
        import unittest.mock as mock
        fs_draft = "NAME: snoop\nNOTES: tries to read a file\nCODE:\nopen('/etc/hostname').read()\n"
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=fs_draft):
            result = propose_capability.propose(self.ledger, self.gateway, self.budget, "read a system file for me")
        self.assertTrue(result["sandbox_result"].startswith("CRASHED:"))
        self.assertIn("SANDBOX_FS_DENIED", result["sandbox_result"])

    def test_nothing_is_ever_executed_or_written_to_disk(self):
        """The one invariant that actually matters here: a draft proposal can never become a
        running capability by itself. gateway.execute() refuses anything not APPROVED, and even
        once approved, kind "capability_proposal" has adapter=None (local record only) - there is
        no code path from a proposal row to an imported/executed module."""
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=DRAFT_REPLY):
            result = propose_capability.propose(self.ledger, self.gateway, self.budget, "tell me tomorrow's weather")
        from apex.kernel.gateway import GatewayError
        with self.assertRaises(GatewayError):
            self.gateway.execute(result["proposal_id"])  # still PENDING, not APPROVED
        self.assertEqual(propose_capability.CAPABILITY_PROPOSAL_KIND.adapter, None)


if __name__ == "__main__":
    unittest.main()


class RecurringGapsTests(unittest.TestCase):
    """Phase D (SUPERIOR_OS_PLAN_20261113.md): let the capability registry grow through this
    pipeline, with a real count-based reminder - never an automatic proposal."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_no_history_means_no_reminder(self):
        self.assertEqual(propose_capability.recurring_gaps(self.ledger), [])

    def test_below_threshold_is_not_surfaced(self):
        facts.assert_fact(self.ledger, "owner", "capability_gap", "tell me tomorrow's weather", "voice:unmet_request", now=1.0)
        facts.assert_fact(self.ledger, "owner", "capability_gap", "tell me tomorrow's weather", "voice:unmet_request", now=2.0)
        self.assertEqual(propose_capability.recurring_gaps(self.ledger), [])

    def test_three_identical_repeats_are_surfaced_with_a_real_count(self):
        for t in (1.0, 2.0, 3.0):
            facts.assert_fact(self.ledger, "owner", "capability_gap", "tell me tomorrow's weather", "voice:unmet_request", now=t)
        out = propose_capability.recurring_gaps(self.ledger)
        self.assertEqual(out, [{"text": "tell me tomorrow's weather", "count": 3}])

    def test_different_wording_is_never_merged_exact_match_only(self):
        facts.assert_fact(self.ledger, "owner", "capability_gap", "tell me the weather", "voice:unmet_request", now=1.0)
        facts.assert_fact(self.ledger, "owner", "capability_gap", "tell me the weather tomorrow", "voice:unmet_request", now=2.0)
        facts.assert_fact(self.ledger, "owner", "capability_gap", "what's the weather", "voice:unmet_request", now=3.0)
        self.assertEqual(propose_capability.recurring_gaps(self.ledger), [])


if __name__ == "__main__":
    unittest.main()
