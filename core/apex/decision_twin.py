"""Decision Twin: uncertainty structure, ABSTAIN rules and autonomy calibration. Status: TESTS_NOT_RUN.

Manifesto requirements implemented: output carries confidence, evidence_count, supporting_patterns, counterfactual, risk_level, abstain_reason and human_override_required; any contradiction,
low confidence, or financial/legal/medical consequence ends in ABSTAIN with the decision handed to the non-internal approval page; self-reported confidence never authorises more autonomy -
autonomy is capped by calibration measured against labelled outcomes. Numeric thresholds below are NOT given by the specification: they are conservative placeholders for the owner to set.
This module scores and decides nothing about the world; it only classifies a proposed decision record. Pure functions, no model or network calls.
"""
from __future__ import annotations

from dataclasses import dataclass

from .agent_contract import AgentOutput, ContractError, parse_output

RISK_LEVELS = ("low", "medium", "high")
CONSEQUENCE_DOMAINS = frozenset({"financial", "legal", "medical"})
MIN_CONFIDENCE = 0.6            # placeholder, owner-adjustable
MIN_EVIDENCE = 2                # placeholder, owner-adjustable
MIN_LABELLED_OUTCOMES = 30      # placeholder, owner-adjustable
MAX_BRIER_FOR_PROMOTION = 0.20  # placeholder, owner-adjustable (0 = perfect, 0.25 = uninformative)
AUTONOMY_LEVELS = (1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class TwinDecision:
    contract: AgentOutput
    evidence_count: int
    supporting_patterns: tuple
    counterfactual: str
    risk_level: str
    decision: str                      # "PROPOSE" or "ABSTAIN"
    abstain_reason: str | None
    human_override_required: bool


def assess(payload: dict, consequence_domains=()) -> TwinDecision:
    """Validate a Decision Twin record and apply the ABSTAIN rules. `consequence_domains` is set by the orchestrator, never by the model."""
    contract = parse_output(payload)
    patterns, counterfactual, risk = payload.get("supporting_patterns"), payload.get("counterfactual"), payload.get("risk_level")
    declared = payload.get("evidence_count")
    if not isinstance(patterns, list) or not all(isinstance(x, str) and x for x in patterns):
        raise ContractError("supporting_patterns must be a list of strings")
    if not isinstance(counterfactual, str) or not counterfactual.strip():
        raise ContractError("counterfactual is required")
    if risk not in RISK_LEVELS:
        raise ContractError("risk_level must be low, medium or high")
    actual = {e for e in contract.evidence} | {e for c in contract.claims for e in c.evidence_ids}
    if type(declared) is not int or declared < 0 or declared > len(actual):
        raise ContractError("evidence_count must be an integer not exceeding the distinct evidence references supplied")
    consequence = frozenset(consequence_domains) & CONSEQUENCE_DOMAINS
    unknown = frozenset(consequence_domains) - CONSEQUENCE_DOMAINS
    if unknown:
        raise ContractError("unknown consequence domain")
    reason = None
    if contract.contradictions:
        reason = "CONTRADICTIONS_PRESENT"
    elif contract.confidence < MIN_CONFIDENCE:
        reason = "LOW_CONFIDENCE"
    elif declared < MIN_EVIDENCE:
        reason = "INSUFFICIENT_EVIDENCE"
    elif consequence:
        reason = "CONSEQUENTIAL_DOMAIN:" + ",".join(sorted(consequence))
    elif risk == "high":
        reason = "HIGH_RISK"
    return TwinDecision(contract, declared, tuple(patterns), counterfactual.strip(), risk,
                        "ABSTAIN" if reason else "PROPOSE", reason, reason is not None)


def brier_score(labelled):
    """Mean squared error between stated confidence and the labelled outcome (True/False). Lower is better."""
    items = list(labelled)
    if not items or not all(isinstance(c, (int, float)) and 0 <= c <= 1 and isinstance(o, bool) for c, o in items):
        raise ValueError("labelled outcomes must be (confidence 0..1, bool) pairs")
    return sum((c - (1.0 if o else 0.0)) ** 2 for c, o in items) / len(items)


def earned_autonomy(requested, labelled):
    """Autonomy level the evidence supports: L1 always; one extra level per full block of labelled outcomes while calibration stays good.

    Never reads the model's own confidence as a licence. Promotion beyond what is earned is refused; promotion itself still needs explicit human approval.
    """
    if requested not in AUTONOMY_LEVELS:
        raise ValueError("autonomy level must be 1..6")
    items = list(labelled)
    if len(items) < MIN_LABELLED_OUTCOMES or brier_score(items) > MAX_BRIER_FOR_PROMOTION:
        return 1
    earned = min(6, 1 + len(items) // MIN_LABELLED_OUTCOMES)
    return min(requested, earned)
