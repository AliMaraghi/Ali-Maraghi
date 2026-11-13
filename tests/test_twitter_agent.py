"""A-20 Twitter/X agent: read-only mentions, budget-gated LLM draft, structurally cannot post."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from apex import twitter_agent
from apex.kernel.memory import Ledger
from apex.kernel.budget import Budget, BudgetDenied

TOKEN = "t" * 40


class Fake:
    def __init__(self, body, status=200):
        self.body, self.status, self.calls = body, status, []

    def __call__(self, method, path, headers):
        self.calls.append((method, path, headers))
        if method != "GET":
            raise AssertionError("twitter_agent must never call anything but GET")
        return self.status, "application/json", json.dumps(self.body).encode()


class CredentialTests(unittest.TestCase):
    def test_missing_token_file(self):
        with mock.patch.object(twitter_agent, "TOKEN_FILE", Path("/nonexistent/twitter-token.json")):
            with self.assertRaises(twitter_agent.TwitterAgentError):
                twitter_agent.load_credentials()


class MentionsTests(unittest.TestCase):
    def test_fetches_bounded_mentions(self):
        fake = Fake({"data": [{"id": "1", "text": "hello @ali"}]})
        rows = twitter_agent.fetch_mentions(TOKEN, "999", fake)
        self.assertEqual(rows, [{"id": "1", "text": "hello @ali"}])
        self.assertEqual(fake.calls[0][0], "GET")

    def test_no_mentions_key_means_empty_not_error(self):
        rows = twitter_agent.fetch_mentions(TOKEN, "999", Fake({}))
        self.assertEqual(rows, [])

    def test_tier_limit_403_fails_closed_with_real_status(self):
        with self.assertRaisesRegex(twitter_agent.TwitterAgentError, "TWITTER_HTTP_403"):
            twitter_agent.fetch_mentions(TOKEN, "999", Fake({}, status=403))

    def test_oversized_page_is_rejected(self):
        body = {"data": [{"id": str(i), "text": "x"} for i in range(15)]}
        with self.assertRaises(twitter_agent.TwitterAgentError):
            twitter_agent.fetch_mentions(TOKEN, "999", Fake(body), max_results=10)


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_save_draft_rejects_oversized_text(self):
        with self.assertRaises(ValueError):
            twitter_agent.save_draft(self.ledger, "1", "x" * 281, time.time())

    def test_zero_budget_by_default_blocks_llm_draft(self):
        with self.assertRaises(BudgetDenied):
            twitter_agent.generate_and_save_draft(self.budget, self.ledger, "1", "hello", "run1")
        self.assertEqual(twitter_agent.list_drafts(self.ledger), [])

    def test_generated_draft_is_saved_never_posted(self):
        self.budget.set_price("anthropic", "twitter-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch("apex.twitter_agent.load_api_key", return_value="fake-key"), \
             mock.patch("apex.twitter_agent.call_anthropic", return_value="Thanks for the mention!"):
            twitter_agent.generate_and_save_draft(self.budget, self.ledger, "mention-1", "hello", "run1")
        drafts = twitter_agent.list_drafts(self.ledger)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["draft_text"], "Thanks for the mention!")
        self.assertEqual(drafts[0]["status"], "DRAFT")

    def test_llm_failure_releases_the_reservation(self):
        self.budget.set_price("anthropic", "twitter-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch("apex.twitter_agent.load_api_key", side_effect=twitter_agent.ResearchPipelineError("x")):
            with self.assertRaises(twitter_agent.ResearchPipelineError):
                twitter_agent.generate_and_save_draft(self.budget, self.ledger, "1", "hello", "run1")
        # a released reservation must not count against the cap on the next attempt
        self.assertEqual(self.budget.spent("core", "day", time.time()), 0)


if __name__ == "__main__":
    unittest.main()
