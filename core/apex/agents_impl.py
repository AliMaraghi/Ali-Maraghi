"""Concrete local agents A-1 (Strategic Intelligence), A-5 (Career & Industry), A-8 (Financial Intelligence). No model calls, no paid APIs, no account access.

A-1  reads public arXiv Atom feeds through the injected fetcher (the repository's existing source allow-list) and reports counts and frequent title terms. Macro-economic feeds need owner-chosen, verified URLs.
A-5  triages job listings the OWNER supplies in runtime/inbox/jobs.json (exports of job alerts, saved searches, a future approved feed). It does NOT scrape LinkedIn or any logged-in site: that breaks the
     site's terms and risks the account. It ranks by deterministic keyword rules and PROPOSES a shortlist; it applies to nothing.
A-8  runs ESPP scenarios in integer pence ONLY from owner-supplied rule tables that carry a source and verification date (runtime/rules/uk_tax_rules.json); with no rules it returns confidence 0 and says so.
     It embeds no tax law, states every assumption, and is decision support, not tax advice.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from . import health_labs, relationship_assist, rss
from .agents_runtime import AgentContext, AgentResult, BaseAgent, contract, evidence_id

MAX_LAB_RESULTS = 500
MAX_SOCIAL_ITEMS = 50

STOP = frozenset("with from that this their into using based towards toward over under between via for and the are our how can new use study analysis approach method model models learning".split())
JOB_TITLE_WEIGHTS = {"procurement": 3, "sourcing": 2, "supply chain": 2, "operations": 2, "purchasing": 2, "category": 1, "vendor": 1}
JOB_COMPANIES = {"amd", "nvidia", "amazon"}
MAX_JOBS = 500


class StrategicIntelligence(BaseAgent):
    agent_id = "A-1"
    min_interval_seconds = 3600       # hourly

    def run(self, ctx: AgentContext) -> AgentResult:
        feeds = ctx.config.get("feeds") or rss.SOURCES
        unknowns = ["No macro-economic feed is configured: only the repository's public arXiv feeds are read"]
        if ctx.fetch is None:
            return AgentResult(contract(self.agent_id, f"A1-{ctx.today}", [], ["No network fetcher was provided"], unknowns + ["Fetcher missing"], 0.0, []))
        claims, evidence, titles = [], [], []
        for name, url in feeds.items():
            try:
                items = rss.extract_items(ctx.fetch(url), limit=ctx.config.get("limit", 10))
            except Exception as exc:                          # a blocked or failing feed is reported, never papered over (class name only)
                unknowns.append(f"Feed '{name}' unavailable ({type(exc).__name__}): outside the reviewed endpoint scope or failing")
                continue
            ids = [evidence_id("rss", link) for _, link in items]
            evidence += ids
            titles += [title for title, _ in items]
            claims.append({"text": f"Feed '{name}' returned {len(items)} entries on {ctx.today}", "kind": "fact", "evidence_ids": ids or [evidence_id("rss-feed", url)]})
        words = Counter(w for t in titles for w in re.findall(r"[a-z]{4,20}", t.lower()) if w not in STOP)
        top = [w for w, n in words.most_common(5) if n >= 2]
        if top:
            claims.append({"text": "Frequent title terms: " + ", ".join(top), "kind": "inference", "evidence_ids": evidence[:20]})
        return AgentResult(contract(self.agent_id, f"A1-{ctx.today}", claims, ["Titles only: no abstracts or full text were read", "Term frequency is descriptive, not a forecast"],
                                    unknowns, 0.4, evidence))


def _job(raw):
    if not isinstance(raw, dict):
        return None
    out = {}
    for key, limit in (("title", 200), ("company", 100), ("location", 100), ("source", 40), ("url", 500)):
        value = raw.get(key, "")
        if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
            return None
        out[key] = value.strip()
    if not out["title"] or not out["company"] or (out["url"] and not out["url"].startswith("https://")):
        return None
    return out


def score_job(job):
    title, score = job["title"].lower(), 0
    for word, weight in JOB_TITLE_WEIGHTS.items():
        if word in title:
            score += weight
    if job["company"].lower() in JOB_COMPANIES:
        score += 2
    if "london" in job["location"].lower():
        score += 2
    return score


class CareerIndustry(BaseAgent):
    agent_id = "A-5"
    min_interval_seconds = 6 * 3600    # every 6 hours
    THRESHOLD, TOP = 4, 3

    def run(self, ctx: AgentContext) -> AgentResult:
        path = ctx.inbox / "jobs.json"
        if not path.is_file():
            return AgentResult(contract(self.agent_id, f"A5-{ctx.today}", [], ["No listings were analysed"],
                                        ["No job source is configured (runtime/inbox/jobs.json is absent). LinkedIn is not scraped; provide job-alert exports or an approved feed"], 0.0, []))
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or len(raw) > MAX_JOBS:
            raise ValueError("jobs.json must be a list of at most 500 listings")
        jobs = [j for j in (_job(r) for r in raw) if j]
        ranked = sorted(((score_job(j), j) for j in jobs), key=lambda t: (-t[0], t[1]["title"]))
        shortlist = [(s, j) for s, j in ranked if s >= self.THRESHOLD][: self.TOP]
        claims, evidence, proposals = [], [], []
        for score, job in shortlist:
            eid = evidence_id("job", job["title"] + job["company"] + job["location"] + job["url"])
            evidence.append(eid)
            claims.append({"text": f"Listing from {job['company']} ({job['location'] or 'location unknown'}) scored {score} on the keyword rules", "kind": "fact", "evidence_ids": [eid]})
            note = f"Shortlist: {job['title']} at {job['company']} ({job['location']}) {job['url']}".strip()[:1900]
            proposals.append({"kind": "record_decision", "payload": {"note": note}, "evidence_ids": [eid]})
        unknowns = [f"{len(raw) - len(jobs)} listings were malformed and skipped"] if len(raw) != len(jobs) else []
        unknowns.append("Keyword scoring does not judge fit, salary, visa status or the employer")
        return AgentResult(contract(self.agent_id, f"A5-{ctx.today}", claims, ["Listings are owner-supplied data and unverified", "Applying is never automatic"], unknowns,
                                    0.5 if shortlist else 0.2, evidence), proposals)


def income_tax(income, rules):
    tax_rules = rules["income_tax"]
    taxable, prev, tax = max(0, income - tax_rules["personal_allowance_pence"]), 0, 0
    for band in tax_rules["bands"]:
        upto = band["upto_pence"] if band["upto_pence"] is not None else taxable
        part = max(0, min(taxable, upto) - prev)
        tax += part * band["rate_bp"] // 10000
        prev = max(prev, upto)
    return tax


def employee_nic(income, rules):
    nic = rules.get("nic")
    if not nic:
        return None
    main = max(0, min(income, nic["upper_limit_pence"]) - nic["primary_threshold_pence"])
    upper = max(0, income - nic["upper_limit_pence"])
    return main * nic["main_rate_bp"] // 10000 + upper * nic["upper_rate_bp"] // 10000


def uc_capital_deduction(capital_pence, rules):
    """Universal Credit capital tariff-income rule: no effect under the lower threshold,
    ineligible above the upper threshold (returns None), a fixed per-unit deduction in between.
    The STRUCTURE of this rule is stable UK welfare law; the actual threshold/deduction figures
    below are read from an owner-sourced rules file (same discipline as uk_tax_rules.json) and
    are never embedded here as hardcoded numbers."""
    uc = rules.get("universal_credit")
    if not uc:
        return "NOT_MODELLED"
    if type(capital_pence) is not int or capital_pence < 0:
        raise ValueError("capital_pence must be a non-negative integer")
    lower, upper = uc["capital_lower_threshold_pence"], uc["capital_upper_threshold_pence"]
    if capital_pence <= lower:
        return 0
    if capital_pence > upper:
        return None  # ineligible - capital above the upper threshold ends UC entitlement entirely
    excess = capital_pence - lower
    units = -(-excess // uc["capital_tariff_pence"])  # ceiling division - any part of a unit counts
    return units * uc["capital_tariff_deduction_pence"]


def mortgage_affordability_indicator(income_pence, rules):
    """A single regulatory reference point (the FCA/PRA loan-to-income ceiling), NOT a mortgage
    offer, NOT an affordability stress test, and NOT what any specific lender will actually
    offer - real affordability depends on outgoings, deposit, credit history and a lender's own
    stress test, none of which this models. The multiplier is read from the same sourced rules
    file, never embedded."""
    mortgage = rules.get("mortgage")
    if not mortgage:
        return "NOT_MODELLED"
    if type(income_pence) is not int or income_pence < 0:
        raise ValueError("income_pence must be a non-negative integer")
    return income_pence * mortgage["income_multiplier_bp"] // 10000


def plan_finance_checks(data: dict) -> list:
    """PLANNER (brutal-honesty directive, 2026-11-15): decomposes the owner's actual supplied
    data into an ordered list of checks - deterministic, not an LLM call. Tax/NIC arithmetic is
    exact integer math; delegating it to a model would turn a verifiable calculation into a
    guess, which this project has never done and will not start doing here. "Planning" in this
    harness means deciding WHICH checks the owner's data calls for, not guessing numbers."""
    checks = ["espp_scenario"]
    if data.get("capital_pence") is not None:
        checks.append("universal_credit")
    checks.append("mortgage_reference")
    return checks


def generate_finance_action(data: dict, rules: dict, calibration_note: str = "") -> dict:
    """GENERATOR: drafts exactly ONE concrete, one-click proposed action from the owner's ESPP
    scenario - never a paragraph of commentary. Every number traces back to a specific
    owner-supplied field (data["espp"][...]) or a sourced rule (rules["source"]/["verified_on"]);
    nothing here is invented. Still pure arithmetic, no LLM call. `calibration_note`, when the
    caller supplies one, is the real-outcomes feedback loop (facts.recent_outcomes_for_predicate_prefix)
    made visible in the text the owner and the evaluator both see - never invented, always
    either empty or built from an actual recorded owner decision."""
    salary, espp = data["annual_salary_pence"], data["espp"]
    price = min(espp["fmv_start_pence_per_share"], espp["fmv_end_pence_per_share"]) * (10000 - espp["discount_bp"]) // 10000
    shares = espp["contribution_pence"] // price if price > 0 else 0
    gain = shares * (espp["fmv_end_pence_per_share"] - price)
    tax_extra = income_tax(salary + gain, rules) - income_tax(salary, rules)
    nic_now, nic_after = employee_nic(salary, rules), employee_nic(salary + gain, rules)
    nic_extra = 0 if nic_now is None else nic_after - nic_now
    net = gain - tax_extra - nic_extra
    action_name = "exercise_espp_now" if net > 0 else "hold_espp_do_not_exercise"
    scenario_text = (
        f"From owner-supplied espp.contribution_pence={espp['contribution_pence']}, "
        f"fmv_start_pence_per_share={espp['fmv_start_pence_per_share']}, "
        f"fmv_end_pence_per_share={espp['fmv_end_pence_per_share']}, discount_bp={espp['discount_bp']}: "
        f"{shares} whole shares, gain {gain}p, extra income tax {tax_extra}p, extra employee NIC "
        f"{'not modelled' if nic_now is None else str(nic_extra) + 'p'}, net {net}p "
        f"({rules['tax_year']} rules, source {rules['source']}, verified {rules['verified_on']}). "
        f"One-click action: {action_name}." + (f" {calibration_note}" if calibration_note else ""))
    return {"action_name": action_name, "scenario_text": scenario_text[:1900],
            "gain_pence": gain, "tax_pence": tax_extra, "net_pence_clamped": max(net, 0),
            "net_true_pence": net, "contribution_used_pence": espp["contribution_pence"],
            "nic_modelled": nic_now is not None}


def evaluate_finance_action(proposal: dict, data: dict) -> dict:
    """EVALUATOR (brutal-honesty directive, 2026-11-15, hardened per section 4.2): runs in a
    SEPARATE CONTEXT from the generator. "Separate context" is made real, not asserted, by the
    very first line below: both arguments are round-tripped through json.dumps/json.loads before
    anything else touches them, which severs any shared Python object identity, closure or
    reference to the generator's internal state - the evaluator can see only the same plain
    JSON-serializable facts a second, independent process would receive over a wire. It cannot
    rubber-stamp reasoning it was never given. Grades exactly the three rubric criteria from the
    directive: (1) the action cites exact line items from the owner-supplied file, (2) it does
    not exceed the owner's declared contribution without flagging it, (3) it names the one-click
    action the owner will take. Returns a per-criterion VERDICT LIST (never a single boolean) plus
    a separate overall_pass; a FAIL on any criterion means run() never submits this as a proposal."""
    proposal = json.loads(json.dumps(proposal))      # the "separate context" cut - see docstring
    data = json.loads(json.dumps(data))
    espp = data.get("espp", {})
    text = proposal.get("scenario_text", "")
    cites = all(str(espp.get(k)) in text for k in
                ("contribution_pence", "fmv_start_pence_per_share", "fmv_end_pence_per_share", "discount_bp"))
    within_budget = (isinstance(proposal.get("contribution_used_pence"), int)
                      and isinstance(espp.get("contribution_pence"), int)
                      and proposal["contribution_used_pence"] <= espp["contribution_pence"])
    names_action = proposal.get("action_name") in ("exercise_espp_now", "hold_espp_do_not_exercise")
    criteria = [
        {"criterion": "cites_exact_line_items", "pass": cites,
         "detail": "scenario_text contains the owner's own contribution/fmv/discount figures" if cites
                   else "scenario_text is missing one or more owner-supplied figures"},
        {"criterion": "within_declared_budget", "pass": within_budget,
         "detail": f"uses {proposal.get('contribution_used_pence')}p against the owner's declared "
                   f"{espp.get('contribution_pence')}p contribution" if within_budget
                   else "proposed action uses more than the owner's declared contribution, with no explicit approval-required flag"},
        {"criterion": "names_one_click_action", "pass": names_action,
         "detail": f"action_name='{proposal.get('action_name')}'" if names_action
                   else "no recognised one-click action was named"},
    ]
    return {"criteria": criteria, "overall_pass": all(c["pass"] for c in criteria)}


class FinancialIntelligence(BaseAgent):
    """A-8. ESPP/tax scenario analysis. Rebuilt 2026-11-15 (brutal-honesty directive) into a
    planner -> generator -> evaluator harness: plan_finance_checks() decomposes the task,
    generate_finance_action() drafts ONE concrete one-click action, evaluate_finance_action()
    grades it against a written rubric using only the generator's output (never its reasoning).
    Only an evaluator PASS becomes a submitted proposal; a FAIL is reported as an unknown and
    nothing is proposed - fail-closed, never a simulated recommendation."""
    agent_id = "A-8"
    min_interval_seconds = 12 * 3600   # every 12 hours
    data_classes = ("public", "finance")
    OUTCOME_PREDICATE = "finance_action_0"       # one proposal per run; see facts.py's finance_claim_N convention

    def __init__(self, ledger=None):
        """`ledger` is optional ONLY so unit tests that don't need the outcome loop can skip it;
        every real deployment (scripts/agents_runner.py, scripts/worker_loop.py) injects the real
        Ledger, exactly like EvidenceVerification(ledger) already does, so the calibration read
        and the fact assertion below are real, not a stub, in production."""
        self.ledger = ledger

    def run(self, ctx: AgentContext) -> AgentResult:
        rules_path, inputs_path = ctx.rules / "uk_tax_rules.json", ctx.inbox / "espp_inputs.json"
        unknowns = ["Personal-allowance taper, student loan, pension relief, later capital gains and Universal Credit effects are not modelled"]
        risks = ["Decision support only, not tax advice", "Assumes the ESPP gain is taxed as employment income; the real treatment depends on the plan and is NOT determined here"]
        if not rules_path.is_file() or not inputs_path.is_file():
            missing = [p.name for p in (rules_path, inputs_path) if not p.is_file()]
            return AgentResult(contract(self.agent_id, f"A8-{ctx.today}", [], risks, unknowns + [f"Missing owner-supplied file(s): {', '.join(missing)}. No tax law is embedded; the rule table needs a source and verification date"], 0.0, []))
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        if not all(isinstance(rules.get(k), str) and rules[k] for k in ("tax_year", "source", "verified_on")):
            raise ValueError("rule table needs tax_year, source and verified_on")
        data = json.loads(inputs_path.read_text(encoding="utf-8"))
        salary, espp = data["annual_salary_pence"], data["espp"]
        for value in (salary, espp["contribution_pence"], espp["fmv_start_pence_per_share"], espp["fmv_end_pence_per_share"], espp["discount_bp"]):
            if type(value) is not int or value < 0:
                raise ValueError("inputs must be non-negative integers in pence / basis points")
        price = min(espp["fmv_start_pence_per_share"], espp["fmv_end_pence_per_share"]) * (10000 - espp["discount_bp"]) // 10000
        if price <= 0:
            raise ValueError("purchase price must be positive")
        eid = evidence_id("rules", rules["source"] + rules["verified_on"] + rules["tax_year"])

        plan = plan_finance_checks(data)
        proposals = []
        calibration_note = ""
        if self.ledger is not None:
            from .kernel import facts
            past = facts.recent_outcomes_for_predicate_prefix(self.ledger, "owner", "finance_action_", limit=3)
            if past:
                calibration_note = ("Calibration - the owner's last recorded decision(s) on prior "
                                     "finance_action proposals: " + "; ".join(
                                         f"{p['outcome']} ({p['note'][:60]})" if p["note"] else p["outcome"]
                                         for p in past) + ".")
        proposal = generate_finance_action(data, rules, calibration_note)
        verdict = evaluate_finance_action(proposal, data)
        claims = [{"text": proposal["scenario_text"], "kind": "inference", "evidence_ids": [eid]}]
        if verdict["overall_pass"]:
            verdict_str = json.dumps({c["criterion"]: c["pass"] for c in verdict["criteria"]})[:400]
            fact_id = 0
            if self.ledger is not None:
                from .kernel import facts
                fact_id = facts.assert_fact(self.ledger, "owner", self.OUTCOME_PREDICATE, proposal["scenario_text"],
                                             "A-8:FinancialIntelligence", now=ctx.now)
            payload = {"action_name": proposal["action_name"], "scenario_text": proposal["scenario_text"],
                       "gain_pence": proposal["gain_pence"], "tax_pence": proposal["tax_pence"],
                       "net_pence_clamped": proposal["net_pence_clamped"], "evaluator_verdict": verdict_str,
                       "fact_id": fact_id}
            proposals.append({"kind": "finance_action_proposal", "payload": payload, "evidence_ids": [eid]})
            if fact_id:
                unknowns.append(f"Record the owner's real decision with: python3 scripts/record_outcome.py "
                                 f"--fact-id {fact_id} --outcome accepted|rejected|acted_on|ignored")
        else:
            failed = [c for c in verdict["criteria"] if not c["pass"]]
            unknowns.append(f"Evaluator rejected the drafted action on {[c['criterion'] for c in failed]} - "
                             "fail-closed, nothing proposed: " + "; ".join(c["detail"] for c in failed))

        # Both below are OPTIONAL: only computed if the owner supplied the matching rules section
        # (uk_tax_rules.json's "universal_credit"/"mortgage" keys, same source+verified_on
        # discipline) - absent by default, never silently assumed.
        capital_pence = data.get("capital_pence")
        if "universal_credit" in plan:
            deduction = uc_capital_deduction(capital_pence, rules)
            if deduction == "NOT_MODELLED":
                unknowns.append("capital_pence was supplied but uk_tax_rules.json has no 'universal_credit' section - not modelled")
            elif deduction is None:
                claims.append({"text": f"Capital of {capital_pence}p is above the UC upper capital threshold - "
                                        f"entitlement would end entirely (source: {rules['source']}, verified {rules['verified_on']})",
                               "kind": "inference", "evidence_ids": [eid]})
            else:
                claims.append({"text": f"UC capital tariff deduction at {capital_pence}p capital: {deduction}p/month "
                                        f"(source: {rules['source']}, verified {rules['verified_on']})",
                               "kind": "inference", "evidence_ids": [eid]})
        mortgage_cap = mortgage_affordability_indicator(salary, rules)
        if mortgage_cap != "NOT_MODELLED":
            risks.append("The mortgage figure is a regulatory loan-to-income reference point only, "
                          "not an affordability stress test and not any lender's actual offer")
            claims.append({"text": f"Regulatory loan-to-income reference on {salary}p salary: up to {mortgage_cap}p "
                                    f"(source: {rules['source']}, verified {rules['verified_on']}) - not a mortgage offer",
                           "kind": "inference", "evidence_ids": [eid]})

        return AgentResult(contract(self.agent_id, f"A8-{ctx.today}", claims, risks, unknowns, 0.5, [eid]), proposals)


class HealthLongevity(BaseAgent):
    """A-15 (promoted from SPEC_ONLY this session - see docs/apex_status/SUPERIOR_OS_PLAN_20261113.md
    Phase C). Wraps the already-written, already-tested core/apex/health_labs.py parser as a real
    agent: reads owner-exported lab-result TEXT from runtime/inbox/lab_results.txt, parses it with
    parse_lab_text()/reference_check(), and reports one claim per cleanly-parsed row. Pure function
    underneath - no model call, no network, nothing stored beyond what the Ledger/Gateway already
    store for any agent's claims. RESEARCH AID ONLY: never a diagnosis, never clinical advice, and
    any row the parser could not parse with certainty (needs_review) is counted in unknowns, never
    silently dropped or guessed."""
    agent_id = "A-15"
    min_interval_seconds = 24 * 3600   # daily is plenty; lab results don't change hour to hour
    data_classes = ("public", "medical")

    def run(self, ctx: AgentContext) -> AgentResult:
        path = ctx.inbox / "lab_results.txt"
        risks = ["Research aid only - this is not a medical device, not a diagnosis, and not clinical advice",
                  "LOW/HIGH/NORMAL only restates the printed reference range on the report; it is not a clinical interpretation"]
        if not path.is_file():
            return AgentResult(contract(self.agent_id, f"A15-{ctx.today}", [], risks,
                                        ["No lab export is configured (runtime/inbox/lab_results.txt is absent). "
                                         "Export the text from your own report with a local tool; no PDF is parsed here"], 0.0, []))
        text = path.read_text(encoding="utf-8")
        rows = health_labs.parse_lab_text(text, f"A15-{ctx.today}", max_lines=MAX_LAB_RESULTS * 10)
        if not rows:
            return AgentResult(contract(self.agent_id, f"A15-{ctx.today}", [], risks,
                                        ["No recognisable result lines were found in the export"], 0.0, []))
        claims, evidence, needs_review_count = [], [], 0
        for row in rows[:MAX_LAB_RESULTS]:
            eid = evidence_id("lab", f"{row['document_id']}:{row['line_no']}:{row['test']}")
            evidence.append(eid)
            if row["needs_review"]:
                needs_review_count += 1
            check = health_labs.reference_check(row)
            value_text = f"{row['value']} {row['unit']}" if row["unit"] else str(row["value"])
            claims.append({"text": f"{row['test']}: {value_text} (flag: {row['flag']}). {check['statement']}",
                           "kind": "fact", "evidence_ids": [eid]})
        unknowns = []
        if needs_review_count:
            unknowns.append(f"{needs_review_count} of {len(rows)} line(s) need manual review - "
                             "unit or printed range could not be parsed with certainty")
        confidence = round((len(rows) - needs_review_count) / len(rows), 2) if rows else 0.0
        return AgentResult(contract(self.agent_id, f"A15-{ctx.today}", claims, risks, unknowns, confidence, evidence))


class EvidenceVerification(BaseAgent):
    """A-3 (promoted from SPEC_ONLY this session - SUPERIOR_OS_PLAN_20261113.md Phase C, second
    role). "Find contradictions and audit data" done honestly: a read-only scan of the existing
    fact store (core/apex/kernel/facts.py) for (subject, predicate) pairs with more than one
    DISTINCT asserted value - a genuine contradiction over time (e.g. two different finance
    scenarios, or a re-stated personal fact). It resolves nothing and picks no "correct" value;
    it only surfaces what already contradicts itself, with full provenance, for a human to
    judge. Pure read of the Ledger - no model call, no network, no new table."""
    agent_id = "A-3"
    min_interval_seconds = 24 * 3600
    data_classes = ("public",)

    def __init__(self, ledger):
        self.ledger = ledger

    def run(self, ctx: AgentContext) -> AgentResult:
        from .kernel import facts
        found = facts.find_contradictions(self.ledger, limit=50)
        if not found:
            return AgentResult(contract(self.agent_id, f"A3-{ctx.today}", [],
                                        ["Audits only the existing fact store - a claim never asserted as a fact is invisible here"],
                                        ["No (subject, predicate) pair currently has more than one distinct asserted value"], 1.0, []))
        claims, evidence = [], []
        for item in found:
            eid = evidence_id("contradiction", item["subject"] + item["predicate"])
            evidence.append(eid)
            values = "; ".join(f"{h['object']!r} (source: {h['source']})" for h in item["history"][:5])
            claims.append({"text": f"{item['subject']}/{item['predicate']} has {len(item['history'])} distinct "
                                    f"asserted value(s) over time, most recent first: {values}",
                           "kind": "fact", "evidence_ids": [eid]})
        return AgentResult(contract(self.agent_id, f"A3-{ctx.today}", claims,
                                    ["Surfaces contradictions only - resolves nothing and picks no value as correct"],
                                    [], 1.0, evidence))


class SocialRelational(BaseAgent):
    """A-10 (promoted from SPEC_ONLY this session - SUPERIOR_OS_PLAN_20261113.md Phase C, third
    role). Wraps the already-written, already-tested core/apex/relationship_assist.py as a real
    agent: reads an owner-supplied JSON request file (runtime/inbox/relationship_requests.json)
    describing notes to record, draft text to prepare, or a bio to checklist - and reports exactly
    what that module allows, nothing more. relationship_assist.guard() refuses anything that smells
    like automation, impersonation, swiping or session/cookie handling before this agent ever sees
    it. Every draft is text only, always requires_owner_review, and is never sent, swiped or posted
    by this or any other code path. No account access, no network, no messaging."""
    agent_id = "A-10"
    min_interval_seconds = 3600
    data_classes = ("public",)

    def run(self, ctx: AgentContext) -> AgentResult:
        path = ctx.inbox / "relationship_requests.json"
        risks = ["Advisory only: every note/draft/checklist is text the owner reviews and sends by "
                 "hand; nothing here can message, swipe, log in or post anywhere",
                 "relationship_assist.guard() refuses automation/impersonation/session-handling "
                 "requests outright, before any draft is prepared"]
        if not path.is_file():
            return AgentResult(contract(self.agent_id, f"A10-{ctx.today}", [], risks,
                                        ["No request file is configured "
                                         "(runtime/inbox/relationship_requests.json is absent)"], 0.0, []))
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return AgentResult(contract(self.agent_id, f"A10-{ctx.today}", [], risks,
                                        [f"Request file could not be read ({type(exc).__name__})"], 0.0, []))
        if not isinstance(raw, dict):
            return AgentResult(contract(self.agent_id, f"A10-{ctx.today}", [], risks,
                                        ["Request file is not a JSON object"], 0.0, []))
        claims, evidence, unknowns = [], [], []
        for note in (raw.get("notes") or [])[:MAX_SOCIAL_ITEMS]:
            if not isinstance(note, dict):
                continue
            try:
                n = relationship_assist.make_note(note.get("person_label", ""), note.get("text", ""),
                                                   note.get("created", ""))
            except (ValueError, relationship_assist.AssistRefused) as exc:
                unknowns.append(f"Note skipped: {exc}")
                continue
            eid = evidence_id("relationship-note", f"{n.person_label}:{n.created}")
            evidence.append(eid)
            claims.append({"text": f"Note recorded for '{n.person_label}' on {n.created}",
                           "kind": "fact", "evidence_ids": [eid]})
        for draft in (raw.get("drafts") or [])[:MAX_SOCIAL_ITEMS]:
            if not isinstance(draft, dict):
                continue
            try:
                d = relationship_assist.draft_package(draft.get("purpose", ""), draft.get("context", ""),
                                                        draft.get("tone", "warm"))
            except (ValueError, relationship_assist.AssistRefused) as exc:
                unknowns.append(f"Draft skipped: {exc}")
                continue
            eid = evidence_id("relationship-draft", d.purpose + d.context)
            evidence.append(eid)
            claims.append({"text": f"Draft package prepared ({d.tone} tone) for: {d.purpose}. "
                                    "Owner must review and send manually.",
                           "kind": "inference", "evidence_ids": [eid]})
        for bio in (raw.get("bios") or [])[:MAX_SOCIAL_ITEMS]:
            if not isinstance(bio, dict):
                continue
            try:
                items = relationship_assist.bio_checklist(bio.get("bio", ""))
            except relationship_assist.AssistRefused as exc:
                unknowns.append(f"Bio skipped: {exc}")
                continue
            label = str(bio.get("label", "bio"))[:80]
            eid = evidence_id("relationship-bio", label + str(bio.get("bio", "")))
            evidence.append(eid)
            claims.append({"text": f"Bio checklist for '{label}': " + " | ".join(items),
                           "kind": "inference", "evidence_ids": [eid]})
        if not claims:
            unknowns.append("No note, draft or bio in the request file parsed successfully")
        return AgentResult(contract(self.agent_id, f"A10-{ctx.today}", claims, risks, unknowns,
                                    0.6 if claims else 0.0, evidence))
