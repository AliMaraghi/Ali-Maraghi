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

from . import rss
from .agents_runtime import AgentContext, AgentResult, BaseAgent, contract, evidence_id

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


class FinancialIntelligence(BaseAgent):
    agent_id = "A-8"
    min_interval_seconds = 12 * 3600   # every 12 hours
    data_classes = ("public", "finance")

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
        shares = espp["contribution_pence"] // price
        gain = shares * (espp["fmv_end_pence_per_share"] - price)
        tax_extra = income_tax(salary + gain, rules) - income_tax(salary, rules)
        nic_now, nic_after = employee_nic(salary, rules), employee_nic(salary + gain, rules)
        nic_extra = None if nic_now is None else nic_after - nic_now
        net = gain - tax_extra - (nic_extra or 0)
        eid = evidence_id("rules", rules["source"] + rules["verified_on"] + rules["tax_year"])
        claims = [{"text": f"Scenario ({rules['tax_year']} rules verified {rules['verified_on']}): {shares} whole shares, gain {gain}p, extra income tax {tax_extra}p, "
                           f"extra employee NIC {'not modelled' if nic_extra is None else str(nic_extra) + 'p'}, net after those {net}p", "kind": "inference", "evidence_ids": [eid]}]

        # Both below are OPTIONAL: only computed if the owner supplied the matching rules section
        # (uk_tax_rules.json's "universal_credit"/"mortgage" keys, same source+verified_on
        # discipline) - absent by default, never silently assumed.
        capital_pence = data.get("capital_pence")
        if capital_pence is not None:
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

        return AgentResult(contract(self.agent_id, f"A8-{ctx.today}", claims, risks, unknowns, 0.5, [eid]))
