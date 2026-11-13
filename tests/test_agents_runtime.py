"""Governing roster, BaseAgent runtime and the three local agents. Rule tables below are SYNTHETIC test numbers, not statements about UK law."""
import json
import tempfile
import unittest
from pathlib import Path

from apex import agents_governing as gov
from apex import agents_registry as legacy
from apex.agents_impl import CareerIndustry, FinancialIntelligence, StrategicIntelligence, income_tax
from apex.agents_runtime import AgentContext, AgentResult, AgentRunner, BaseAgent, contract
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway
from apex.kernel.memory import Ledger

ATOM = ("<feed xmlns='http://www.w3.org/2005/Atom'>" + "".join(
    f"<entry><id>http://arxiv.org/abs/2401.0000{i}v1</id><title>Efficient transformers for planning {i}</title></entry>" for i in range(1, 4)) + "</feed>").encode()
JOBS = [
    {"title": "Supply Chain Operations Lead", "company": "Amazon", "location": "London", "url": "https://example.test/1", "source": "alert"},
    {"title": "Procurement Manager", "company": "AMD", "location": "London", "url": "https://example.test/2", "source": "alert"},
    {"title": "Operations Analyst", "company": "NVIDIA", "location": "London", "url": "https://example.test/3", "source": "alert"},
    {"title": "Software Engineer", "company": "AMD", "location": "London", "url": "https://example.test/4", "source": "alert"},
    {"title": "Chef", "company": "Bistro", "location": "Paris", "url": "https://example.test/5", "source": "alert"},
    {"title": "Bad", "company": "X", "location": "L", "url": "http://insecure.example", "source": "alert"},
]
RULES = {"tax_year": "SYNTHETIC", "source": "https://example.test/rules", "verified_on": "2026-01-01",
         "income_tax": {"personal_allowance_pence": 1257000, "bands": [{"upto_pence": 3770000, "rate_bp": 2000}, {"upto_pence": 12514000, "rate_bp": 4000}, {"upto_pence": None, "rate_bp": 4500}]},
         "nic": {"primary_threshold_pence": 1257000, "upper_limit_pence": 5027000, "main_rate_bp": 800, "upper_rate_bp": 200}}
INPUTS = {"annual_salary_pence": 6_000_000, "espp": {"contribution_pence": 150_000, "fmv_start_pence_per_share": 5000, "fmv_end_pence_per_share": 6000, "discount_bp": 1500}}


class RuntimeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "inbox").mkdir()
        (self.root / "rules").mkdir()
        self.ledger = Ledger(self.root)
        self.book = ApprovalBook(self.ledger, b"k" * 32, clock=lambda: 1_800_000_000.0)
        self.gateway = ActionGateway(self.ledger, self.book, Budget(self.ledger))
        self.ctx = AgentContext(now=1_800_000_000.0, today="2027-01-15", inbox=self.root / "inbox", rules=self.root / "rules", fetch=lambda url: ATOM)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def runner(self, agents, notifier=None):
        return AgentRunner(self.ledger, self.gateway, agents, notifier=notifier, clock=lambda: 1_800_000_000.0)


class RosterTests(unittest.TestCase):
    def test_eighteen_roles_four_implemented(self):
        self.assertEqual([r.agent_id for r in gov.ROLES], [f"A-{n}" for n in range(1, 19)])
        self.assertEqual([r.agent_id for r in gov.ROLES if r.status == gov.IMPLEMENTED_LOCAL], ["A-1", "A-2", "A-5", "A-8"])
        self.assertEqual(gov.get("A-3").legacy_slot, "8-12")
        self.assertEqual(gov.get("A-5").name, "Career & Industry")

    def test_data_class_isolation(self):
        self.assertTrue(gov.check_inputs("A-8", ["public", legacy.FINANCE]))
        for agent, classes in (("A-5", [legacy.FINANCE]), ("A-1", [legacy.MEDICAL]), ("A-8", [legacy.EMPLOYER])):
            with self.assertRaises(legacy.IsolationError):
                gov.check_inputs(agent, classes)
        with self.assertRaisesRegex(legacy.IsolationError, "CORPORATE_SOURCE_DENIED"):
            gov.check_inputs("A-1", ["public"], data_source="corporate")


class CareerTests(RuntimeBase):
    def test_shortlist_becomes_pending_proposals_and_only_once(self):
        (self.root / "inbox" / "jobs.json").write_text(json.dumps(JOBS))
        notices = []
        now = [1_800_000_000.0]
        runner = AgentRunner(self.ledger, self.gateway, [CareerIndustry()], notifier=lambda pid, kind: notices.append((pid, kind)), clock=lambda: now[0])
        first = runner.run_once(self.ctx)[0]
        self.assertEqual(first["status"], "OK")
        self.assertEqual([p["state"] for p in first["proposals"]], ["PENDING"] * 3)
        self.assertEqual(len(notices), 3)
        views = [self.book.view(p["id"]) for p in first["proposals"]]
        notes = [v["payload"]["note"] for v in views]
        self.assertTrue(notes[0].startswith("Shortlist: Supply Chain Operations Lead at Amazon"))
        self.assertTrue(notes[1].startswith("Shortlist: Procurement Manager at AMD"))
        self.assertTrue(notes[2].startswith("Shortlist: Operations Analyst at NVIDIA"))
        self.assertTrue(all(v["state"] == "PENDING" for v in views))                 # nothing executed or approved
        now[0] += CareerIndustry.min_interval_seconds                                 # past A-5's own schedule, so this call is a genuine re-run, not a skip
        again = runner.run_once(self.ctx)[0]
        self.assertEqual([p["state"] for p in again["proposals"]], ["DUPLICATE"] * 3)
        self.assertEqual(len(notices), 3)

    def test_no_source_means_no_invention(self):
        out = self.runner([CareerIndustry()]).run_once(self.ctx)[0]
        self.assertEqual((out["confidence"], out["claims"], out["proposals"]), (0.0, 0, []))
        self.assertIn("LinkedIn is not scraped", out["unknowns"][0])

    def test_notice_failure_never_loses_the_proposal(self):
        (self.root / "inbox" / "jobs.json").write_text(json.dumps(JOBS))

        def boom(pid, kind):
            raise RuntimeError("telegram down")
        out = self.runner([CareerIndustry()], notifier=boom).run_once(self.ctx)[0]
        self.assertEqual(len(out["proposals"]), 3)
        self.assertEqual(out["notice_error"], "RuntimeError")


class FinancialTests(RuntimeBase):
    def test_no_rules_no_numbers(self):
        out = self.runner([FinancialIntelligence()]).run_once(self.ctx)[0]
        self.assertEqual((out["confidence"], out["claims"]), (0.0, 0))
        self.assertIn("No tax law is embedded", out["unknowns"][-1])

    def test_scenario_arithmetic_in_integer_pence(self):
        (self.root / "rules" / "uk_tax_rules.json").write_text(json.dumps(RULES))
        (self.root / "inbox" / "espp_inputs.json").write_text(json.dumps(INPUTS))
        agent = FinancialIntelligence()
        text = agent.run(self.ctx).contract["claims"][0]["text"]
        for part in ("35 whole shares", "gain 61250p", "extra income tax 24500p", "extra employee NIC 1225p", "net after those 35525p"):
            self.assertIn(part, text)
        self.assertEqual(income_tax(6_000_000, RULES), 1_143_200)
        self.assertEqual(self.runner([agent]).run_once(self.ctx)[0]["proposals"], [])          # financial output never proposes actions

    def test_rule_table_without_source_is_rejected(self):
        (self.root / "rules" / "uk_tax_rules.json").write_text(json.dumps({**RULES, "source": ""}))
        (self.root / "inbox" / "espp_inputs.json").write_text(json.dumps(INPUTS))
        out = self.runner([FinancialIntelligence()]).run_once(self.ctx)[0]
        self.assertEqual((out["status"], out["error"]), ("ERROR", "ValueError"))


class StrategicTests(RuntimeBase):
    def test_feed_counts_and_terms_without_titles_in_claims(self):
        result = StrategicIntelligence().run(self.ctx)
        texts = [c["text"] for c in result.contract["claims"]]
        self.assertTrue(any("returned 3 entries" in t for t in texts))
        self.assertTrue(any("transformers" in t and "planning" in t for t in texts))
        self.assertFalse(any("Efficient transformers for planning 1" in t for t in texts))
        self.assertEqual(result.contract["confidence"], 0.4)
        self.assertEqual(result.proposals, [])

    def test_no_fetcher_no_claims(self):
        self.ctx.fetch = None
        out = StrategicIntelligence().run(self.ctx).contract
        self.assertEqual((out["confidence"], out["claims"]), (0.0, []))


class RunnerSafetyTests(RuntimeBase):
    def test_errors_are_isolated_and_text_is_not_recorded(self):
        class Boom(BaseAgent):
            agent_id = "A-1"

            def run(self, ctx):
                raise ValueError("SECRET-TEXT-IN-ERROR")
        class Fine(CareerIndustry):
            pass
        out = self.runner([Boom(), Fine()]).run_once(self.ctx)
        self.assertEqual((out[0]["status"], out[0]["error"]), ("ERROR", "ValueError"))
        self.assertEqual(out[1]["status"], "OK")
        self.assertNotIn("SECRET-TEXT", json.dumps(self.ledger.records("opportunity")))

    def test_spec_only_agents_and_wrong_agent_id_are_refused(self):
        class NotBuilt(BaseAgent):
            agent_id = "A-3"       # still SPEC_ONLY; A-2 was implemented this session (agents_research.ScientificResearch)
        class Impostor(BaseAgent):
            agent_id = "A-1"

            def run(self, ctx):
                return AgentResult(contract("A-5", "t", [], [], [], 0.1, []))
        out = self.runner([NotBuilt(), Impostor()]).run_once(self.ctx)
        self.assertEqual((out[0]["status"], out[0]["error"]), ("ERROR", "PermissionError"))
        self.assertEqual((out[1]["status"], out[1]["error"]), ("ERROR", "ContractError"))

    def test_durable_stop_blocks_every_agent(self):
        self.ledger.db.execute("CREATE TABLE IF NOT EXISTS job_meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, stop TEXT NOT NULL)")
        self.ledger.db.execute("INSERT OR REPLACE INTO job_meta VALUES (1,1,'STOP_EXECUTION')")
        out = self.runner([StrategicIntelligence(), CareerIndustry()]).run_once(self.ctx)
        self.assertEqual([o["error"] for o in out], ["PermissionError", "PermissionError"])

    def test_every_run_is_journaled(self):
        self.runner([CareerIndustry(), FinancialIntelligence()]).run_once(self.ctx)
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity") + self.ledger.records("personal")]
        self.assertEqual(events.count("agent_run"), 2)
        self.assertGreater(self.ledger.verify(), 0)

class IntervalSchedulingTests(RuntimeBase):
    def test_hourly_agent_is_skipped_until_due_then_runs(self):
        now = [1_800_000_000.0]
        self.ctx = AgentContext(now=now[0], today="2027-01-15", inbox=self.root / "inbox", rules=self.root / "rules", fetch=lambda url: ATOM)
        runner = AgentRunner(self.ledger, self.gateway, [StrategicIntelligence()], clock=lambda: now[0])
        first = runner.run_once(self.ctx)[0]
        self.assertEqual(first["status"], "OK")
        now[0] += 60
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "SKIPPED_TOO_SOON")
        now[0] += 3600
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "OK")

    def test_different_agents_have_independent_schedules(self):
        now = [1_800_000_000.0]
        runner = self.runner([StrategicIntelligence(), FinancialIntelligence()])
        runner.clock = lambda: now[0]
        first = runner.run_once(self.ctx)
        self.assertEqual([r["status"] for r in first], ["OK", "OK"])
        now[0] += 3700
        second = runner.run_once(self.ctx)
        self.assertEqual([r["status"] for r in second], ["OK", "SKIPPED_TOO_SOON"])

    def test_an_erroring_agent_is_still_marked_run_and_not_retried_immediately(self):
        class Boom(StrategicIntelligence):
            def run(self, ctx):
                raise ValueError("x")
        now = [1_800_000_000.0]
        runner = AgentRunner(self.ledger, self.gateway, [Boom()], clock=lambda: now[0])
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "ERROR")
        now[0] += 10
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "SKIPPED_TOO_SOON")


class IntervalSchedulingTests(RuntimeBase):
    def test_hourly_agent_is_skipped_until_due_then_runs(self):
        now = [1_800_000_000.0]
        self.ctx = AgentContext(now=now[0], today="2027-01-15", inbox=self.root / "inbox", rules=self.root / "rules", fetch=lambda url: ATOM)
        runner = AgentRunner(self.ledger, self.gateway, [StrategicIntelligence()], clock=lambda: now[0])
        first = runner.run_once(self.ctx)[0]
        self.assertEqual(first["status"], "OK")
        now[0] += 60
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "SKIPPED_TOO_SOON")
        now[0] += 3600
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "OK")

    def test_different_agents_have_independent_schedules(self):
        now = [1_800_000_000.0]
        runner = self.runner([StrategicIntelligence(), FinancialIntelligence()])
        runner.clock = lambda: now[0]
        first = runner.run_once(self.ctx)
        self.assertEqual([r["status"] for r in first], ["OK", "OK"])
        now[0] += 3700
        second = runner.run_once(self.ctx)
        self.assertEqual([r["status"] for r in second], ["OK", "SKIPPED_TOO_SOON"])

    def test_an_erroring_agent_is_still_marked_run_and_not_retried_immediately(self):
        class Boom(StrategicIntelligence):
            def run(self, ctx):
                raise ValueError("x")
        now = [1_800_000_000.0]
        runner = AgentRunner(self.ledger, self.gateway, [Boom()], clock=lambda: now[0])
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "ERROR")
        now[0] += 10
        self.assertEqual(runner.run_once(self.ctx)[0]["status"], "SKIPPED_TOO_SOON")


if __name__ == "__main__":
    unittest.main()


class BenefitAndMortgageTests(RuntimeBase):
    def test_uc_capital_not_modelled_without_rules_section(self):
        from apex.agents_impl import uc_capital_deduction
        self.assertEqual(uc_capital_deduction(100, RULES), "NOT_MODELLED")

    def test_uc_capital_tariff_bands(self):
        from apex.agents_impl import uc_capital_deduction
        rules = {**RULES, "universal_credit": {
            "capital_lower_threshold_pence": 600_000, "capital_upper_threshold_pence": 1_600_000,
            "capital_tariff_pence": 25_000, "capital_tariff_deduction_pence": 435}}
        self.assertEqual(uc_capital_deduction(500_000, rules), 0)            # under lower threshold
        self.assertEqual(uc_capital_deduction(600_000, rules), 0)            # exactly at lower threshold
        self.assertEqual(uc_capital_deduction(610_000, rules), 435)          # one partial unit (ceiling)
        self.assertEqual(uc_capital_deduction(625_000, rules), 435)          # exactly one unit
        self.assertEqual(uc_capital_deduction(650_000, rules), 870)          # exactly two units
        self.assertIsNone(uc_capital_deduction(1_600_001, rules))            # above upper -> ineligible

    def test_mortgage_affordability_not_modelled_without_rules_section(self):
        from apex.agents_impl import mortgage_affordability_indicator
        self.assertEqual(mortgage_affordability_indicator(6_000_000, RULES), "NOT_MODELLED")

    def test_mortgage_affordability_applies_income_multiplier(self):
        from apex.agents_impl import mortgage_affordability_indicator
        rules = {**RULES, "mortgage": {"income_multiplier_bp": 45000}}  # 4.5x
        self.assertEqual(mortgage_affordability_indicator(4_200_000, rules), 18_900_000)

    def test_financial_agent_includes_uc_and_mortgage_claims_when_supplied(self):
        rules = {**RULES,
                 "universal_credit": {"capital_lower_threshold_pence": 600_000, "capital_upper_threshold_pence": 1_600_000,
                                       "capital_tariff_pence": 25_000, "capital_tariff_deduction_pence": 435},
                 "mortgage": {"income_multiplier_bp": 45000}}
        (self.root / "rules" / "uk_tax_rules.json").write_text(json.dumps(rules))
        (self.root / "inbox" / "espp_inputs.json").write_text(json.dumps({**INPUTS, "capital_pence": 700_000}))
        texts = [c["text"] for c in FinancialIntelligence().run(self.ctx).contract["claims"]]
        self.assertTrue(any("UC capital tariff deduction" in t and "1740p/month" in t for t in texts))
        self.assertTrue(any("Regulatory loan-to-income reference" in t for t in texts))

    def test_without_capital_pence_or_mortgage_section_nothing_extra_is_added(self):
        (self.root / "rules" / "uk_tax_rules.json").write_text(json.dumps(RULES))
        (self.root / "inbox" / "espp_inputs.json").write_text(json.dumps(INPUTS))
        claims = FinancialIntelligence().run(self.ctx).contract["claims"]
        self.assertEqual(len(claims), 1)  # just the ESPP scenario, nothing fabricated


if __name__ == "__main__":
    unittest.main()
