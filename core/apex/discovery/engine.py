"""Deterministic, read-only discovery/criticism experiment.

No LLM, network, external account, payment, publication, or database writes.
A title alone is NOT empirical evidence of a commercial opportunity.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

VERSION = "apex-rde-r1.0-offline"
ALLOWED_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}

@dataclass(frozen=True)
class Signal:
    title: str
    url: str
    source: str = "arxiv-rss"
    observed_at: str | None = None
    synthetic: bool = False

def allowed_public_source(url: str) -> bool:
    if not isinstance(url, str): return False
    try:
        p = urlsplit(url)
        return (p.scheme == "https" and p.hostname in ALLOWED_HOSTS
                and not p.username and not p.password and p.port in (None, 443)
                and not p.fragment and len(url) <= 2000)
    except (TypeError, ValueError):
        return False

def _normalized_title(title: str) -> str:
    if not isinstance(title, str): return ""
    return " ".join(title.split())[:280]

def blocked(reason: str, *, source: str = "none") -> dict:
    return {
        "engine_version": VERSION,
        "status": reason,
        "source": source,
        "empirical_superiority_proven": False,
        "autonomous_actions": [],
        "api_calls": 0,
        "billable_ai_spend_usd": 0,
        "promotion": {"decision": "REJECT", "why": "Required empirical evidence absent"},
    }

def run_cycle(signal: Signal) -> dict:
    """One offline run with alternatives and explicit failed validation gates.

    The output creates TESTABLE QUESTIONS, not validated findings.
    All source content is treated as inert data, never instructions.
    """
    title = _normalized_title(signal.title)
    if not title:
        return blocked("BLOCKED_EMPTY_TITLE", source=signal.source)
    if not allowed_public_source(signal.url):
        return blocked("BLOCKED_UNTRUSTED_SOURCE", source=signal.source)

    unique = json.dumps({"title": title, "url": signal.url},sort_keys=True,ensure_ascii=False)
    input_hash = hashlib.sha256(unique.encode("utf-8")).hexdigest()
    hypotheses = [
        {
            "id": "H1", "kind": "initial_hypothesis",
            "claim": "This research item may signal near-term demand for an economic opportunity.",
            "disconfirmation": "No independent buyer demand or defensible use case is found.",
        },
        {
            "id": "H2", "kind": "counterfactual",
            "claim": "The item could be scientifically interesting but commercially premature.",
            "disconfirmation": "Independent evidence shows urgent purchasing demand now.",
        },
        {
            "id": "H3", "kind": "counterfactual_and_negative_space",
            "claim": "Value, if any, may instead lie in an overlooked adjacent workflow or user group.",
            "disconfirmation": "An adjacent user-group review reveals no unmet workflow, willingness to pay, or adoption bottleneck.",
        },
    ]
    critiques = [
        {"id":"C1","status":"OPEN","finding":"A title and link do not establish results, method quality, or even a relevant abstract."},
        {"id":"C2","status":"OPEN","finding":"arXiv posting is not proof of independent peer review or reproducibility."},
        {"id":"C3","status":"OPEN","finding":"No independent customer, payment, or market-demand evidence has been checked."},
        {"id":"C4","status":"OPEN","finding":"Observation time is not necessarily the paper's publication date."},
        {"id":"C5","status":"OPEN","finding":"Costs, competitors, relevant rights, and route to a reversible trial are unknown."},
    ]
    plan = [
        {"step":1,"type":"research","requires_approval":False,"task":"Read the actual abstract and full paper; check methods, limits, publication date and authors.","done":False},
        {"step":2,"type":"evidence","requires_approval":False,"task":"Locate at least two independent sources addressing the same need, including credible contrary evidence.","done":False},
        {"step":3,"type":"market","requires_approval":True,"task":"Assess real competitor offerings and ask prospective buyers whether they would pay; obtain consent before outreach.","done":False},
        {"step":4,"type":"economics","requires_approval":False,"task":"Estimate actual costs, risks, expected value and an affordable reversible experiment.","done":False},
    ]
    checks = {
        "source_url_allowlisted": True,
        "three_distinct_hypothesis_positions_present": len({x["id"] for x in hypotheses}) >= 3,
        "at_least_two_counterfactuals": sum(h["id"] in ("H2","H3") for h in hypotheses) >= 2,
        "critic_objections_present": len(critiques) >= 4,
        "independent_source_verified": False,
        "full_text_methods_reviewed": False,
        "real_buyer_evidence_verified": False,
        "independent_baseline_benchmark_completed": False,
    }
    structural_pass = all(checks[k] for k in (
        "source_url_allowlisted", "three_distinct_hypothesis_positions_present",
        "at_least_two_counterfactuals", "critic_objections_present"))
    empirical_pass = all(checks[k] for k in (
        "independent_source_verified", "full_text_methods_reviewed",
        "real_buyer_evidence_verified", "independent_baseline_benchmark_completed"))
    return {
        "engine_version": VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED_PENDING_EVIDENCE" if not empirical_pass else "ELIGIBLE_FOR_HUMAN_REVIEW",
        "mode": "OFFLINE_STRUCTURAL_TRIAL_NOT_INTELLIGENCE_BENCHMARK",
        "input_sha256": input_hash,
        "signal": {
            "title": title, "url": signal.url, "source": str(signal.source)[:80],
            "observed_at": signal.observed_at,
            "is_synthetic_fixture": bool(signal.synthetic),
            "source_content_trust": "UNTRUSTED_DATA_ONLY",
            "evidence_level": "RSS_TITLE_ONLY_NOT_INDEPENDENTLY_VERIFIED",
        },
        "problem_discovery": {"question": "Does this research signal suggest any verifiable, lawful and affordable economic opportunity?", "initial_assumption": hypotheses[0]["claim"]},
        "invention_engine": {
            "hypotheses": hypotheses,
            "negative_space_questions": [
                "Which overlooked user group might experience a costly unsolved workflow?",
                "Which important need is absent from existing products or study framing?",
            ],
            "innovation_status": "QUESTIONS_ONLY_NOT_DISCOVERIES",
        },
        "critic": {"objections": critiques, "stance": "INITIAL_CLAIM_NOT_SUBSTANTIATED"},
        "empirical_lab": {
            "checks": checks, "structural_gate_passed": structural_pass,
            "empirical_gate_passed": empirical_pass,
            "validated_opportunity_count": 0,
            "baseline_comparison": {
                "status": "NOT_RUN",
                "why": "No independent ChatGPT/Claude/human baseline measured; counting hypotheses alone cannot prove superiority",
            },
            "next_validation_steps": plan,
        },
        "evolutionary_memory": {
            "record_type": "UNVERIFIED_CANDIDATE",
            "champion_promoted": False,
            "learning_claimed": False,
            "next_action": "Collect independent evidence and a held-out benchmark before considering promotion",
        },
        "constitution": {"scope": "18-part North Star preserved in separate local reference; not transmitted to an AI provider", "auto_injected_to_llm": False},
        "empirical_superiority_proven": False,
        "autonomous_actions": [],
        "api_calls": 0,
        "billable_ai_spend_usd": 0,
        "promotion": {"decision": "REJECT", "why": "Empirical evidence and baseline benchmark are missing"},
    }
