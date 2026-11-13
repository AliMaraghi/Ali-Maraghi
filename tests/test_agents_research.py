"""A-2 Scientific Research: Planner -> Researcher -> Executor -> Critic, fully offline.
No network: pubmed is driven by a fake transport, and call_anthropic is monkeypatched."""
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from apex import agents_research
from apex.agents_governing import get as governing_get, IMPLEMENTED_LOCAL
from apex.agents_research import ScientificResearch, load_api_key, set_price_and_cap
from apex.agents_runtime import AgentContext
from apex.kernel.budget import Budget, BudgetDenied
from apex.kernel.memory import Ledger
from apex.pubmed import RateLimiter

ESEARCH_JSON = json.dumps({"esearchresult": {"count": "1", "idlist": ["12345678"]}}).encode()
EFETCH_XML = (b"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345678</PMID>"
              b"<Article><ArticleTitle>A real-sounding paper title</ArticleTitle>"
              b"<Abstract><AbstractText>Some abstract text.</AbstractText></Abstract></Article>"
              b"</MedlineCitation></PubmedArticle></PubmedArticleSet>")
ESEARCH_EMPTY = json.dumps({"esearchresult": {"count": "0", "idlist": []}}).encode()


def fake_transport_with_results(method, path, headers):
    if "esearch" in path:
        return 200, "application/json", ESEARCH_JSON
    return 200, "text/xml", EFETCH_XML


def fake_transport_no_results(method, path, headers):
    if "esearch" in path:
        return 200, "application/json", ESEARCH_EMPTY
    return 200, "text/xml", b"<PubmedArticleSet></PubmedArticleSet>"


def instant_limiter():
    return RateLimiter(clock=lambda: 0.0, sleep=lambda s: None)


class ResearchPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)
        (self.root / "runtime" / "inbox").mkdir(parents=True, exist_ok=True)
        self.topics_path = self.root / "runtime" / "inbox" / "research_topics.json"
        import time as _time
        self.ctx = AgentContext(now=_time.time(), today="2026-11-13",
                                 inbox=self.root / "runtime" / "inbox", rules=self.root / "runtime" / "rules")

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def agent(self, transport=fake_transport_with_results):
        return ScientificResearch(self.budget, self.ledger, transport=transport, limiter=instant_limiter())

    # ---- governing roster ---------------------------------------------
    def test_a2_is_implemented_local(self):
        self.assertEqual(governing_get("A-2").status, IMPLEMENTED_LOCAL)

    # ---- missing/empty input --------------------------------------------
    def test_missing_topics_file_is_graceful(self):
        result = self.agent().run(self.ctx)
        self.assertEqual(result.contract["confidence"], 0.0)
        self.assertEqual(result.proposals, [])

    def test_no_pending_topic_is_graceful(self):
        self.topics_path.write_text(json.dumps([{"topic": "old one", "status": "proposed"}]))
        result = self.agent().run(self.ctx)
        self.assertEqual(result.contract["confidence"], 0.0)
        self.assertEqual(result.proposals, [])

    # ---- zero-budget-by-default -----------------------------------------
    def test_zero_budget_by_default_blocks_every_llm_call(self):
        self.topics_path.write_text(json.dumps([{"topic": "quantum batteries", "status": "pending"}]))
        with unittest.mock.patch.object(agents_research, "call_anthropic") as fake_call:
            result = self.agent().run(self.ctx)
        fake_call.assert_not_called()
        self.assertEqual(result.contract["confidence"], 0.0)
        self.assertEqual(result.proposals, [])
        # the topic must NOT be marked proposed - nothing happened, so it stays eligible to retry
        self.assertEqual(json.loads(self.topics_path.read_text())[0]["status"], "pending")

    # ---- full happy path --------------------------------------------------
    def test_full_pipeline_produces_one_proposal_and_marks_topic_processed(self):
        set_price_and_cap(self.root, price_millipence=100, cap_pence=1000)
        self.topics_path.write_text(json.dumps([{"topic": "quantum batteries", "status": "pending"}]))

        responses = iter(["sub-question one\nsub-question two", "Draft citing PMID 12345678.", "APPROVE"])
        with unittest.mock.patch.object(agents_research, "load_api_key", return_value="fake-key"), \
             unittest.mock.patch.object(agents_research, "call_anthropic", side_effect=lambda *a, **k: next(responses)):
            result = self.agent().run(self.ctx)

        self.assertEqual(len(result.proposals), 1)
        payload = result.proposals[0]["payload"]
        self.assertEqual(payload["topic"], "quantum batteries")
        self.assertIn("12345678", payload["draft"])
        self.assertGreater(result.contract["confidence"], 0)
        self.assertEqual(json.loads(self.topics_path.read_text())[0]["status"], "proposed")

    def test_critic_revision_is_bounded_to_one_retry(self):
        set_price_and_cap(self.root, price_millipence=100, cap_pence=10_000)
        self.topics_path.write_text(json.dumps([{"topic": "cold fusion", "status": "pending"}]))

        # plan, draft, critic(REVISE), revised-draft, critic(REVISE again) - must stop after MAX_REVISIONS=1
        responses = iter(["sub-question one", "first draft", "REVISE: too vague",
                          "second draft", "REVISE: still vague"])
        calls = []
        def fake_call(api_key, system, user_text, max_tokens=400):
            calls.append(user_text)
            return next(responses)
        with unittest.mock.patch.object(agents_research, "load_api_key", return_value="fake-key"), \
             unittest.mock.patch.object(agents_research, "call_anthropic", side_effect=fake_call):
            result = self.agent(transport=fake_transport_no_results).run(self.ctx)

        self.assertEqual(len(result.proposals), 1)
        self.assertEqual(result.proposals[0]["payload"]["draft"], "second draft")
        self.assertIn("still vague", result.proposals[0]["payload"]["critic_notes"])
        self.assertEqual(len(calls), 5)   # plan + draft + critic + revise + critic, then stops (bounded)

    def test_no_pubmed_results_still_produces_a_low_confidence_proposal(self):
        set_price_and_cap(self.root, price_millipence=100, cap_pence=1000)
        self.topics_path.write_text(json.dumps([{"topic": "an obscure topic", "status": "pending"}]))
        responses = iter(["sub-question", "no evidence found, stating so plainly", "APPROVE"])
        with unittest.mock.patch.object(agents_research, "load_api_key", return_value="fake-key"), \
             unittest.mock.patch.object(agents_research, "call_anthropic", side_effect=lambda *a, **k: next(responses)):
            result = self.agent(transport=fake_transport_no_results).run(self.ctx)
        self.assertEqual(len(result.proposals), 1)
        self.assertLess(result.contract["confidence"], 0.6)
        self.assertIn("No PubMed evidence", result.contract["unknowns"][0])

    def test_budget_denied_mid_pipeline_releases_cleanly_and_does_not_mark_topic_proposed(self):
        set_price_and_cap(self.root, price_millipence=1000, cap_pence=1)  # exactly one 1p step, no more
        self.topics_path.write_text(json.dumps([{"topic": "too expensive", "status": "pending"}]))
        responses = iter(["sub-question"])
        with unittest.mock.patch.object(agents_research, "load_api_key", return_value="fake-key"), \
             unittest.mock.patch.object(agents_research, "call_anthropic", side_effect=lambda *a, **k: next(responses)):
            result = self.agent(transport=fake_transport_no_results).run(self.ctx)
        self.assertEqual(result.proposals, [])
        self.assertEqual(json.loads(self.topics_path.read_text())[0]["status"], "pending")


class KeyFileTests(unittest.TestCase):
    def test_missing_key_file_raises_clear_error(self):
        with unittest.mock.patch.object(agents_research, "KEY_FILE", Path("/nonexistent/anthropic-key")):
            with self.assertRaises(agents_research.ResearchPipelineError):
                load_api_key()


if __name__ == "__main__":
    unittest.main()
