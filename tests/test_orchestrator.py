"""scripts/orchestrator.py: intent routing, and the RESEARCH_REQUEST -> A-2 queue bridge."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "core"))

import orchestrator  # noqa: E402


class ClassifyTests(unittest.TestCase):
    def test_media_wins_over_everything(self):
        self.assertEqual(orchestrator.classify("make me a video of a sunset"), orchestrator.MEDIA_GENERATION)

    def test_research_request_is_detected(self):
        self.assertEqual(orchestrator.classify("can you research cold fusion for me"), orchestrator.RESEARCH_REQUEST)
        self.assertEqual(orchestrator.classify("is there any evidence that fasting helps"), orchestrator.RESEARCH_REQUEST)

    def test_status_is_detected(self):
        self.assertEqual(orchestrator.classify("what's your budget status"), orchestrator.SYSTEM_STATUS)

    def test_default_is_casual(self):
        self.assertEqual(orchestrator.classify("tell me a joke"), orchestrator.CASUAL_CHAT)

    def test_job_cv_request_is_detected(self):
        self.assertEqual(orchestrator.classify("any update on my job search"), orchestrator.JOB_CV_REQUEST)
        self.assertEqual(orchestrator.classify("help me with my CV"), orchestrator.JOB_CV_REQUEST)


class ResearchQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def topics(self):
        path = self.root / "runtime" / "inbox" / "research_topics.json"
        return json.loads(path.read_text()) if path.is_file() else []

    def test_queue_creates_file_and_pending_entry(self):
        result = orchestrator.queue_research_topic(self.root, "please research quantum batteries")
        self.assertEqual(result, "QUEUED")
        topics = self.topics()
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["status"], "pending")
        self.assertEqual(topics[0]["source"], "voice")
        self.assertNotIn("research", topics[0]["topic"].lower())  # trigger phrase stripped

    def test_queue_is_idempotent_on_same_topic(self):
        orchestrator.queue_research_topic(self.root, "research quantum batteries")
        second = orchestrator.queue_research_topic(self.root, "research quantum batteries")
        self.assertEqual(second, "ALREADY_QUEUED")
        self.assertEqual(len(self.topics()), 1)

    def test_queue_does_not_touch_an_already_proposed_topic(self):
        inbox = self.root / "runtime" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "research_topics.json").write_text(
            json.dumps([{"topic": "cold fusion", "status": "proposed"}]))
        result = orchestrator.queue_research_topic(self.root, "research cold fusion")
        self.assertEqual(result, "ALREADY_QUEUED")
        self.assertEqual(len(self.topics()), 1)

    def test_malformed_topics_file_raises_instead_of_silently_overwriting(self):
        inbox = self.root / "runtime" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "research_topics.json").write_text(json.dumps({"not": "a list"}))
        with self.assertRaises(ValueError):
            orchestrator.queue_research_topic(self.root, "research anything")


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_research_route_is_handled_immediately_and_never_calls_anthropic(self):
        routed = orchestrator.route("please research the health effects of creatine", self.root)
        self.assertEqual(routed["intent"], orchestrator.RESEARCH_REQUEST)
        self.assertTrue(routed["handled"])
        self.assertIn("A-2", routed["reply"])

    def test_casual_chat_is_not_handled_here(self):
        routed = orchestrator.route("how was your day", self.root)
        self.assertFalse(routed["handled"])
        self.assertIsNone(routed["reply"])

    def test_job_cv_route_with_no_prior_run_explains_the_missing_source(self):
        from apex.kernel.memory import Ledger
        with Ledger(self.root):
            pass  # a real ledger always exists by the time voice_api.py calls route() in production
        routed = orchestrator.route("what's happening with my job search", self.root)
        self.assertEqual(routed["intent"], orchestrator.JOB_CV_REQUEST)
        self.assertIn("jobs.json", routed["reply"])

    def test_job_cv_route_reports_the_real_latest_a5_run(self):
        from apex.kernel.memory import Ledger
        with Ledger(self.root) as ledger:
            ledger._append("agentrun.A-5.1", "decision", "opportunity",
                           {"event": "agent_run", "agent": "A-5", "status": "OK", "confidence": 0.6,
                            "claims": 2, "proposals": []})
        routed = orchestrator.route("any news on my CV", self.root)
        self.assertIn("2 listing", routed["reply"])
        self.assertIn("automatic", routed["reply"].lower())


class AgentTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        with Ledger(self.root):
            pass  # a real ledger always exists by the time voice_api.py serves a request

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_root_reports_never_run_and_no_fake_activity(self):
        agents = orchestrator.agent_telemetry(self.root)
        self.assertEqual({a["agent_id"] for a in agents}, {"A-1", "A-2", "A-3", "A-5", "A-8", "A-10", "A-15"})
        for a in agents:
            self.assertEqual(a["status"], "NEVER_RUN")
            self.assertNotEqual(a["status"], "ACTIVE")  # no live-execution signal is ever claimed
            self.assertIsNone(a["last_run_at"])

    def test_a2_blocked_reason_is_the_real_missing_file(self):
        agents = orchestrator.agent_telemetry(self.root)
        a2 = next(a for a in agents if a["agent_id"] == "A-2")
        self.assertTrue(a2["blocked"])
        self.assertIn("research_topics.json", a2["current_task"])

    def test_a2_blocked_reason_clears_once_a_topic_is_pending(self):
        inbox = self.root / "runtime" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "research_topics.json").write_text(json.dumps([{"topic": "x", "status": "pending"}]))
        a2 = next(a for a in orchestrator.agent_telemetry(self.root) if a["agent_id"] == "A-2")
        self.assertFalse(a2["blocked"])
        self.assertIn("PubMed", a2["current_task"])

    def test_last_run_status_and_claims_reflect_the_real_ledger_event(self):
        from apex.kernel.memory import Ledger
        with Ledger(self.root) as ledger:
            ledger._append("agentrun.A-1.1", "decision", "opportunity",
                           {"event": "agent_run", "agent": "A-1", "status": "OK", "confidence": 0.5, "claims": 3})
        a1 = next(a for a in orchestrator.agent_telemetry(self.root) if a["agent_id"] == "A-1")
        self.assertEqual(a1["status"], "OK")
        self.assertEqual(a1["last_claims"], 3)

    def test_error_status_is_reported_not_hidden(self):
        from apex.kernel.memory import Ledger
        with Ledger(self.root) as ledger:
            ledger._append("agentrun.A-8.1", "decision", "personal",
                           {"event": "agent_run", "agent": "A-8", "status": "ERROR", "error": "ValueError"})
        a8 = next(a for a in orchestrator.agent_telemetry(self.root) if a["agent_id"] == "A-8")
        self.assertEqual(a8["status"], "ERROR")
        self.assertEqual(a8["last_error"], "ValueError")

    def test_a2_spend_is_attributed_only_to_a2_keys(self):
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        import time as _time
        with Ledger(self.root) as ledger:
            budget = Budget(ledger)
            budget.set_price("anthropic", "research-pipeline-step", 100, _time.time(), "test")
            budget.set_cap("core", "day", 1000)
            budget.reserve("A-2.1.plan", "core", "anthropic", "research-pipeline-step", 1)
            budget.settle("A-2.1.plan", 1)
        a2 = next(a for a in orchestrator.agent_telemetry(self.root) if a["agent_id"] == "A-2")
        self.assertEqual(a2["calls_today"], 1)
        self.assertGreater(a2["spend_today_pence"], 0)
        a1 = next(a for a in orchestrator.agent_telemetry(self.root) if a["agent_id"] == "A-1")
        self.assertEqual(a1["spend_today_pence"], 0)


if __name__ == "__main__":
    unittest.main()


class TwitterDraftRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_classified_as_twitter_draft(self):
        self.assertEqual(orchestrator.classify("draft a tweet about AMD"), orchestrator.TWITTER_DRAFT_REQUEST)

    def test_without_budget_ledger_args_gives_a_clear_not_wired_reply(self):
        routed = orchestrator.route("draft a tweet about AMD", self.root)
        self.assertTrue(routed["handled"])
        self.assertIn("isn't wired", routed["reply"].lower())

    def test_zero_budget_by_default_blocks_it_and_never_posts(self):
        routed = orchestrator.route("draft a tweet about AMD", self.root, budget=self.budget, ledger=self.ledger)
        self.assertTrue(routed["handled"])
        self.assertIn("budget denied", routed["reply"].lower())

    def test_generated_draft_is_saved_and_reply_says_not_posted(self):
        import unittest.mock as mock
        from apex import twitter_agent
        self.budget.set_price("anthropic", "twitter-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch.object(twitter_agent, "load_api_key", return_value="fake-key"), \
             mock.patch.object(twitter_agent, "call_anthropic", return_value="AMD earnings looked strong this quarter."):
            routed = orchestrator.route("draft a tweet about AMD", self.root, budget=self.budget, ledger=self.ledger)
        self.assertIn("not posted", routed["reply"].lower())
        self.assertEqual(len(twitter_agent.list_drafts(self.ledger)), 1)


if __name__ == "__main__":
    unittest.main()


class FinanceStrategyRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_classified_correctly(self):
        self.assertEqual(orchestrator.classify("give me a financial strategy for my espp"),
                          orchestrator.FINANCE_STRATEGY_REQUEST)

    def test_without_budget_gives_not_wired_reply(self):
        routed = orchestrator.route("run the finance chain", self.root)
        self.assertIn("isn't wired", routed["reply"])

    def test_missing_input_files_is_graceful_and_free(self):
        routed = orchestrator.route("run the finance chain", self.root, budget=self.budget, ledger=self.ledger)
        self.assertIn("No ESPP scenario", routed["reply"])
        self.assertEqual(self.budget.spent("core", "day", time.time()), 0)

    def test_full_chain_runs_a8_then_one_llm_call(self):
        import unittest.mock as mock
        inbox = self.root / "runtime" / "inbox"
        rules = self.root / "runtime" / "rules"
        inbox.mkdir(parents=True)
        rules.mkdir(parents=True)
        (inbox / "espp_inputs.json").write_text(json.dumps({
            "annual_salary_pence": 4200000,
            "espp": {"contribution_pence": 150000, "fmv_start_pence_per_share": 2500,
                      "fmv_end_pence_per_share": 3100, "discount_bp": 1500}}))
        (rules / "uk_tax_rules.json").write_text(json.dumps({
            "tax_year": "2025-26", "source": "GOV.UK", "verified_on": "2026-11-13",
            "income_tax": {"personal_allowance_pence": 1257000,
                            "bands": [{"upto_pence": 5027000, "rate_bp": 2000},
                                      {"upto_pence": None, "rate_bp": 4000}]}}))
        self.budget.set_price("anthropic", "finance-strategy-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="Consider timing the sale carefully."):
            routed = orchestrator.route("run the finance chain", self.root, budget=self.budget, ledger=self.ledger)
        self.assertIn("Recommendation", routed["reply"])
        self.assertIn("timing the sale", routed["reply"])
        self.assertGreater(self.budget.spent("core", "day", time.time()), 0)


if __name__ == "__main__":
    unittest.main()


class AcademicNewsRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_classified_correctly(self):
        self.assertEqual(orchestrator.classify("give me the academic news"), orchestrator.ACADEMIC_NEWS_REQUEST)

    def test_unreachable_feeds_is_graceful_not_a_crash(self):
        def failing_fetch(url):
            raise RuntimeError("blocked")
        routed = orchestrator.route("give me the academic news", self.root, academic_fetch=failing_fetch)
        self.assertIn("Couldn't reach", routed["reply"])

    def test_reports_real_live_fetched_titles(self):
        rss_xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
                   b"<item><title>Real Live Paper Title</title><link>https://arxiv.org/abs/1</link></item>"
                   b"</channel></rss>")

        def fake_fetch(url):
            return rss_xml
        routed = orchestrator.route("university news please", self.root, academic_fetch=fake_fetch)
        self.assertIn("entries on", routed["reply"])
        self.assertIn("A-1", routed["steps"][0])

    def test_academic_latest_titles_is_real_and_bounded(self):
        rss_xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
                   b"<item><title>Real Live Paper Title</title><link>https://arxiv.org/abs/1</link></item>"
                   b"</channel></rss>")

        def fake_fetch(url):
            return rss_xml
        titles = orchestrator.academic_latest_titles(self.root, fetch=fake_fetch, limit=3)
        self.assertTrue(all(t["title"] == "Real Live Paper Title" for t in titles))
        self.assertTrue(all("link" in t and "feed" in t for t in titles))

    def test_academic_latest_titles_empty_on_dead_feeds(self):
        def failing_fetch(url):
            raise RuntimeError("blocked")
        self.assertEqual(orchestrator.academic_latest_titles(self.root, fetch=failing_fetch), [])


if __name__ == "__main__":
    unittest.main()


class DatingDraftRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_classified_correctly(self):
        self.assertEqual(orchestrator.classify("write an opener for this profile: loves hiking"),
                          orchestrator.DATING_DRAFT_REQUEST)

    def test_without_budget_gives_not_wired_reply(self):
        routed = orchestrator.route("dating opener: loves hiking", self.root)
        self.assertIn("isn't wired", routed["reply"])

    def test_zero_budget_by_default_blocks_it(self):
        routed = orchestrator.route("dating opener: loves hiking", self.root, budget=self.budget, ledger=self.ledger)
        self.assertIn("budget denied", routed["reply"].lower())

    def test_generates_and_never_stores_profile_text(self):
        import unittest.mock as mock
        import dating_agent
        self.budget.set_price("anthropic", "dating-draft-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch.object(dating_agent, "load_api_key", return_value="fake-key"), \
             mock.patch.object(dating_agent, "call_anthropic", return_value="1. Hi!\n2. Hey!\n3. Hello!"):
            routed = orchestrator.route("write an opener for this profile: loves hiking", self.root,
                                         budget=self.budget, ledger=self.ledger)
        self.assertIn("Hi!", routed["reply"])
        self.assertIn("Dating assistant", routed["steps"][0])
        tables = {r[0] for r in self.ledger.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("dating_drafts", tables)


if __name__ == "__main__":
    unittest.main()


class DashboardPayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        with Ledger(self.root):
            pass

    def tearDown(self):
        self.tmp.cleanup()

    def test_honest_defaults_with_nothing_configured(self):
        payload = orchestrator.dashboard_payload(self.root)
        self.assertEqual(payload["finance"]["status"], "Needs setup")
        self.assertEqual(payload["academic"]["status"], "Never run")
        self.assertEqual(payload["dating"]["status"], "Needs setup")
        self.assertIn("No scenario run yet", payload["finance"]["metric_en"])

    def test_finance_ready_once_both_files_exist(self):
        inbox = self.root / "runtime" / "inbox"
        rules = self.root / "runtime" / "rules"
        inbox.mkdir(parents=True)
        rules.mkdir(parents=True)
        (inbox / "espp_inputs.json").write_text("{}")
        (rules / "uk_tax_rules.json").write_text("{}")
        payload = orchestrator.dashboard_payload(self.root)
        self.assertEqual(payload["finance"]["status"], "Ready")

    def test_dating_ready_once_priced(self):
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        with Ledger(self.root) as ledger:
            Budget(ledger).set_price("anthropic", "dating-draft-step", 100, time.time(), "test")
        payload = orchestrator.dashboard_payload(self.root)
        self.assertEqual(payload["dating"]["status"], "Ready")

    def test_bilingual_fields_present(self):
        payload = orchestrator.dashboard_payload(self.root)
        for domain in ("finance", "academic", "dating"):
            self.assertIn("metric_fa", payload[domain])
            self.assertIn("action_fa", payload[domain])

    def test_banking_domain_is_honest_needs_setup_with_no_fabricated_score(self):
        payload = orchestrator.dashboard_payload(self.root)
        self.assertIn("banking", payload)
        self.assertEqual(payload["banking"]["status"], "Needs setup")
        self.assertIn("metric_fa", payload["banking"])
        self.assertIn("workflow", payload["banking"])
        self.assertIn("judgement_logic_en", payload["banking"])

    def test_workflow_and_judgement_logic_present_and_bilingual_no_fabricated_scores(self):
        payload = orchestrator.dashboard_payload(self.root)
        for domain in ("finance", "academic", "dating", "banking"):
            d = payload[domain]
            self.assertIsInstance(d["workflow"], list)
            self.assertGreaterEqual(len(d["workflow"]), 2)
            self.assertTrue(all(isinstance(step, str) and step for step in d["workflow"]))
            self.assertIsInstance(d["judgement_logic_en"], str)
            self.assertIsInstance(d["judgement_logic_fa"], str)
            self.assertGreater(len(d["judgement_logic_en"]), 20)
            self.assertGreater(len(d["judgement_logic_fa"]), 20)
            # No invented numeric "scores" anywhere in this payload - see
            # ExecutiveDashboard.jsx's own comment on why.
            self.assertNotIn("score", d["metric_en"].lower())
        self.assertNotIn("respect_score", str(payload))
        self.assertNotIn("relevance", str(payload).lower())
        self.assertNotIn("tax_efficiency", str(payload))


if __name__ == "__main__":
    unittest.main()


class AcademicPersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)
        self.rss_xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
                         b"<item><title>Robotics breakthrough at MIT</title><link>https://arxiv.org/abs/1</link></item>"
                         b"<item><title>Unrelated topic about pastries</title><link>https://arxiv.org/abs/2</link></item>"
                         b"</channel></rss>")

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def fake_fetch(self, url):
        return self.rss_xml

    def test_no_interests_file_stays_generic_and_says_how_to_personalize(self):
        reply, steps = orchestrator.academic_news_reply(self.root, fetch=self.fake_fetch, budget=self.budget)
        self.assertIn("generic", reply.lower())
        self.assertIn("interests.json", reply)

    def test_interests_file_triggers_one_extra_llm_call(self):
        import unittest.mock as mock
        inbox = self.root / "runtime" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "interests.json").write_text(json.dumps(["robotics"]))
        self.budget.set_price("anthropic", "academic-personalize-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="Robotics breakthrough at MIT - matches your interest."):
            reply, steps = orchestrator.academic_news_reply(self.root, fetch=self.fake_fetch, budget=self.budget)
        self.assertIn("Robotics breakthrough", reply)
        self.assertTrue(any("interests.json" in s for s in steps))

    def test_malformed_interests_file_raises_not_silently_ignored(self):
        inbox = self.root / "runtime" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "interests.json").write_text(json.dumps({"not": "a list"}))
        with self.assertRaises(ValueError):
            orchestrator.academic_news_reply(self.root, fetch=self.fake_fetch, budget=self.budget)

    def test_zero_budget_falls_back_to_generic_reply_gracefully(self):
        inbox = self.root / "runtime" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "interests.json").write_text(json.dumps(["robotics"]))
        # No price configured -> budget.reserve() raises BudgetDenied, caught by the broad except,
        # falling through to the generic reply rather than crashing the voice turn.
        reply, steps = orchestrator.academic_news_reply(self.root, fetch=self.fake_fetch, budget=self.budget)
        self.assertIn("generic", reply.lower())


if __name__ == "__main__":
    unittest.main()


class DashboardRealFinanceMetricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_dashboard_shows_real_pound_figure_after_a_voice_finance_request(self):
        import unittest.mock as mock
        inbox = self.root / "runtime" / "inbox"
        rules = self.root / "runtime" / "rules"
        inbox.mkdir(parents=True)
        rules.mkdir(parents=True)
        (inbox / "espp_inputs.json").write_text(json.dumps({
            "annual_salary_pence": 4200000,
            "espp": {"contribution_pence": 150000, "fmv_start_pence_per_share": 2500,
                      "fmv_end_pence_per_share": 3100, "discount_bp": 1500}}))
        (rules / "uk_tax_rules.json").write_text(json.dumps({
            "tax_year": "2025-26", "source": "GOV.UK", "verified_on": "2026-11-13",
            "income_tax": {"personal_allowance_pence": 1257000,
                            "bands": [{"upto_pence": 5027000, "rate_bp": 2000},
                                      {"upto_pence": None, "rate_bp": 4000}]}}))
        self.budget.set_price("anthropic", "finance-strategy-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="Consider timing."):
            orchestrator.finance_strategy_reply(self.budget, self.root, ledger=self.ledger)
        payload = orchestrator.dashboard_payload(self.root)
        self.assertIn("£546.00", payload["finance"]["metric_en"])


if __name__ == "__main__":
    unittest.main()


class LlmRouteFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)
        self.budget.set_price("anthropic", "intent-router-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 1000)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_regex_match_never_calls_the_router(self):
        import unittest.mock as mock
        with mock.patch.object(orchestrator, "llm_route") as fake_router:
            self.assertEqual(orchestrator.classify("academic news", budget=self.budget), orchestrator.ACADEMIC_NEWS_REQUEST)
        fake_router.assert_not_called()

    def test_novel_phrasing_falls_through_to_the_router(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=orchestrator.FINANCE_STRATEGY_REQUEST):
            intent = orchestrator.classify("crunch the numbers on my employee stock plan", budget=self.budget)
        self.assertEqual(intent, orchestrator.FINANCE_STRATEGY_REQUEST)

    def test_router_can_only_return_a_name_from_the_fixed_menu_never_arbitrary_text(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="DROP TABLE events; --"):
            intent = orchestrator.classify("something totally unrelated", budget=self.budget)
        self.assertEqual(intent, orchestrator.CASUAL_CHAT)  # invalid choice -> safe fallback, never executed

    def test_router_says_none_falls_back_to_casual_chat(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="NONE"):
            intent = orchestrator.classify("tell me a joke", budget=self.budget)
        self.assertEqual(intent, orchestrator.CASUAL_CHAT)

    def test_zero_budget_by_default_means_no_router_call_and_safe_fallback(self):
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        unpriced_budget = Budget(Ledger(Path(tempfile.mkdtemp())))
        intent = orchestrator.classify("something totally unrelated to any regex", budget=unpriced_budget)
        self.assertEqual(intent, orchestrator.CASUAL_CHAT)

    def test_without_budget_arg_classify_behaves_exactly_as_before(self):
        self.assertEqual(orchestrator.classify("something totally unrelated to any regex"), orchestrator.CASUAL_CHAT)


if __name__ == "__main__":
    unittest.main()


class FinanceCalibrationTests(unittest.TestCase):
    """Recommendation #1 from the second brutal-honesty self-audit: fact_outcomes must visibly
    change a future finance_strategy_reply, not just sit in a table nothing reads."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)
        inbox = self.root / "runtime" / "inbox"
        rules = self.root / "runtime" / "rules"
        inbox.mkdir(parents=True)
        rules.mkdir(parents=True)
        (inbox / "espp_inputs.json").write_text(json.dumps({
            "annual_salary_pence": 4200000,
            "espp": {"contribution_pence": 150000, "fmv_start_pence_per_share": 2500,
                      "fmv_end_pence_per_share": 3100, "discount_bp": 1500}}))
        (rules / "uk_tax_rules.json").write_text(json.dumps({
            "tax_year": "2025-26", "source": "GOV.UK", "verified_on": "2026-11-13",
            "income_tax": {"personal_allowance_pence": 1257000,
                            "bands": [{"upto_pence": 5027000, "rate_bp": 2000},
                                      {"upto_pence": None, "rate_bp": 4000}]}}))
        self.budget.set_price("anthropic", "finance-strategy-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 10000)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_no_past_outcomes_means_no_calibration_note_and_no_calibration_step(self):
        import unittest.mock as mock
        captured = {}

        def fake_call(api_key, system, user_text, max_tokens=150):
            captured["user_text"] = user_text
            return "Generic advice."

        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", side_effect=fake_call):
            reply, steps = orchestrator.finance_strategy_reply(self.budget, self.root, ledger=self.ledger)
        self.assertNotIn("What happened after past recommendations", captured["user_text"])
        self.assertFalse(any("Calibration" in s for s in steps))

    def test_recorded_rejection_is_included_in_the_prompt_and_reported_as_a_step(self):
        import unittest.mock as mock
        from apex.kernel import facts
        fact_id = facts.assert_fact(self.ledger, "owner", "finance_claim_0",
                                     "Sell immediately at discount.", "A-8:FinancialIntelligence")
        facts.record_outcome(self.ledger, fact_id, "rejected", note="too risky, prices moved against me")

        captured = {}

        def fake_call(api_key, system, user_text, max_tokens=150):
            captured["user_text"] = user_text
            return "Hold longer this time."

        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", side_effect=fake_call):
            reply, steps = orchestrator.finance_strategy_reply(self.budget, self.root, ledger=self.ledger)
        self.assertIn("What happened after past recommendations", captured["user_text"])
        self.assertIn("too risky, prices moved against me", captured["user_text"])
        self.assertIn("rejected", captured["user_text"])
        self.assertTrue(any("Calibration" in s and "1 real recorded outcome" in s for s in steps))

    def test_outcomes_from_other_subjects_or_predicates_never_leak_in(self):
        import unittest.mock as mock
        from apex.kernel import facts
        fid = facts.assert_fact(self.ledger, "owner", "academic_claim_0", "some paper", "A-1")
        facts.record_outcome(self.ledger, fid, "accepted")

        captured = {}

        def fake_call(api_key, system, user_text, max_tokens=150):
            captured["user_text"] = user_text
            return "Generic advice."

        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", side_effect=fake_call):
            orchestrator.finance_strategy_reply(self.budget, self.root, ledger=self.ledger)
        self.assertNotIn("What happened after past recommendations", captured["user_text"])


if __name__ == "__main__":
    unittest.main()


class SequencePlannerTests(unittest.TestCase):
    """Recommendation #2 from the second brutal-honesty self-audit: compose the registered
    capabilities into sequences nobody wrote by hand - bounded to the exact same fixed menu as
    llm_route, never a new action or generated code."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        from apex.kernel.budget import Budget
        self.ledger = Ledger(self.root)
        self.budget = Budget(self.ledger)
        self.budget.set_price("anthropic", "intent-planner-step", 100, time.time(), "test")
        self.budget.set_cap("core", "day", 10000)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_single_step_text_never_triggers_the_planner(self):
        import unittest.mock as mock
        with mock.patch.object(orchestrator, "llm_plan") as fake_plan:
            orchestrator.route("what is the system status", self.root, budget=self.budget, ledger=self.ledger)
        fake_plan.assert_not_called()

    def test_plan_outside_the_fixed_menu_is_rejected_entirely(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic",
                        return_value=f"{orchestrator.SYSTEM_STATUS}, DROP_TABLE_EVERYTHING"):
            plan = orchestrator.llm_plan("check status then also do something else", self.budget)
        self.assertIsNone(plan)

    def test_plan_of_one_name_is_rejected_not_a_sequence(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=orchestrator.SYSTEM_STATUS):
            plan = orchestrator.llm_plan("check status then do more status", self.budget)
        self.assertIsNone(plan)

    def test_valid_two_step_plan_runs_both_capabilities_in_order(self):
        import unittest.mock as mock
        plan_text = f"{orchestrator.SYSTEM_STATUS},{orchestrator.JOB_CV_REQUEST}"
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value=plan_text):
            routed = orchestrator.route("check status then give me the job shortlist",
                                         self.root, budget=self.budget, ledger=self.ledger)
        self.assertTrue(routed["handled"])
        self.assertEqual(routed["intent"], f"SEQUENCE:{orchestrator.SYSTEM_STATUS}+{orchestrator.JOB_CV_REQUEST}")
        self.assertIn(f"[{orchestrator.SYSTEM_STATUS}]", routed["reply"])
        self.assertIn(f"[{orchestrator.JOB_CV_REQUEST}]", routed["reply"])

    def test_no_plan_falls_back_to_ordinary_single_intent_classify(self):
        import unittest.mock as mock
        with mock.patch("apex.agents_research.load_api_key", return_value="fake-key"), \
             mock.patch("apex.agents_research.call_anthropic", return_value="NONE"):
            routed = orchestrator.route("what is the system status then also NONE applies here",
                                         self.root, budget=self.budget, ledger=self.ledger)
        self.assertEqual(routed["intent"], orchestrator.SYSTEM_STATUS)

    def test_without_budget_the_planner_is_never_attempted(self):
        import unittest.mock as mock
        with mock.patch.object(orchestrator, "llm_plan") as fake_plan:
            orchestrator.route("check status then give me the job shortlist", self.root)
        fake_plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class RecurringGapReminderTests(unittest.TestCase):
    """Phase D: system_status_reply surfaces a real recurring-gap count, never fabricated,
    and never breaks the real status line if the reminder lookup fails."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.budget import Budget
        from apex.kernel.memory import Ledger
        with Ledger(self.root) as ledger:
            Budget(ledger)  # pre-create the budget tables, same as real first use - a read-only connection can't create them

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_recurring_gap_no_reminder(self):
        reply = orchestrator.system_status_reply(self.root, "what is the system status")
        self.assertNotIn("you've asked for something like", reply)
        self.assertIn("Voice-API spend today", reply)

    def test_recurring_gap_is_surfaced_with_a_real_count(self):
        from apex.kernel import facts
        from apex.kernel.memory import Ledger
        with Ledger(self.root) as ledger:
            for t in (1.0, 2.0, 3.0):
                facts.assert_fact(ledger, "owner", "capability_gap", "tell me tomorrow's weather", "voice:unmet_request", now=t)
        reply = orchestrator.system_status_reply(self.root, "what is the system status")
        self.assertIn("tell me tomorrow's weather", reply)
        self.assertIn("3 times", reply)


if __name__ == "__main__":
    unittest.main()


class FreshLedgerStatusTests(unittest.TestCase):
    """A genuinely fresh ledger (before Budget's tables are ever created) must not crash
    system_status_reply - found while testing Phase D's reminder wiring."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from apex.kernel.memory import Ledger
        Ledger(self.root).close()  # create the journal file itself, but no Budget tables yet

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_ledger_reports_zero_spend_not_a_crash(self):
        reply = orchestrator.system_status_reply(self.root, "what is the system status")
        self.assertIn("Voice-API spend today: 0p", reply)


if __name__ == "__main__":
    unittest.main()
