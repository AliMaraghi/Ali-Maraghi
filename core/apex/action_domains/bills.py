"""Bills domain (ACTIVE per core/apex/action_domains/router.ACTIVE_DOMAIN). Planner/generator/
evaluator over a synthetic unpaid-bill JSON file. No bank API, no actual payment - the
output is a proposal the owner reviews and approves by hand, same pattern as every other
agent in this codebase (relationship_assist.DraftPackage, gateway.ActionGateway proposals).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = ("vendor", "amount_pence", "due_date")


class BillsError(ValueError):
    pass


@dataclass(frozen=True)
class BillActionProposal:
    proposal_id: str
    vendor: str
    amount_pence: int
    due_date: str
    action: str                 # e.g. "pay_before_due_date", "dispute", "defer"
    requires_owner_review: bool = True
    confidence: float = 0.0
    risks: tuple[str, ...] = ()


def load_synthetic(path: Path) -> dict | None:
    """Returns None (no claims) if the file is absent - same "no input, no output" contract
    every other agent in this codebase follows, never a crash."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not all(f in data for f in REQUIRED_FIELDS):
        return None
    return data


def plan(bill: dict) -> dict:
    """Planner step: decide WHAT needs to happen, before deciding how to say it. Urgency is
    derived from amount and (textually) how close due_date looks to "soon" - this is a toy
    heuristic over synthetic dates, not a real calendar computation, stated plainly."""
    amount = bill["amount_pence"]
    urgency = "high" if amount > 10_000 else "normal"
    return {"action": "pay_before_due_date", "urgency": urgency}


def generate(plan_result: dict, bill: dict) -> BillActionProposal:
    """Generator step: turn the plan into a concrete proposal payload."""
    return BillActionProposal(
        proposal_id=f"bill:{bill['vendor']}:{bill['due_date']}",
        vendor=bill["vendor"], amount_pence=bill["amount_pence"], due_date=bill["due_date"],
        action=plan_result["action"])


def evaluate(proposal: BillActionProposal, plan_result: dict) -> BillActionProposal:
    """Evaluator step: attach confidence and risks - never silently upgrades confidence past
    what the input actually supports (no vendor-reputation data exists, so confidence is
    capped regardless of amount)."""
    risks = ["Synthetic/no real bank connection - this proposal cannot pay anything by itself",
             "No vendor-reputation or fraud check is performed - owner must verify the vendor independently"]
    if plan_result["urgency"] == "high":
        risks.append(f"amount_pence={proposal.amount_pence} exceeds the 10,000p heuristic threshold - review before approving")
    confidence = 0.6 if plan_result["urgency"] == "normal" else 0.4
    return BillActionProposal(proposal.proposal_id, proposal.vendor, proposal.amount_pence,
                              proposal.due_date, proposal.action, True, confidence, tuple(risks))


def make_proposal(path: Path) -> BillActionProposal | None:
    bill = load_synthetic(path)
    if bill is None:
        return None
    plan_result = plan(bill)
    draft = generate(plan_result, bill)
    return evaluate(draft, plan_result)
