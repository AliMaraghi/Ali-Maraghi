"""Calendar domain (STAGED per core/apex/action_domains/router.ACTIVE_DOMAIN == BILLS). Planner/
generator/evaluator over a synthetic calendar-conflict JSON file. No Google Calendar OAuth,
no real calendar access - built and tested so it is ready, not executed by
agents_runner.py --once while a different domain is active.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = ("event_a", "event_b", "conflict_window")


@dataclass(frozen=True)
class CalendarRescheduleProposal:
    proposal_id: str
    conflict_description: str
    proposed_new_time: str
    requires_owner_review: bool = True
    confidence: float = 0.0
    risks: tuple[str, ...] = ()


def load_synthetic(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not all(f in data for f in REQUIRED_FIELDS):
        return None
    return data


def plan(conflict: dict) -> dict:
    """Always proposes moving the SECOND-listed event - a toy heuristic ("the later-added
    one yields"), stated plainly as arbitrary; a real version would need the owner's actual
    priority rules, which do not exist in a synthetic fixture."""
    return {"which_to_move": "event_b"}


def generate(plan_result: dict, conflict: dict) -> CalendarRescheduleProposal:
    moved = conflict[plan_result["which_to_move"]]
    description = f"\"{conflict['event_a']}\" overlaps \"{conflict['event_b']}\" during {conflict['conflict_window']}"
    return CalendarRescheduleProposal(
        proposal_id=f"calendar:{conflict['event_a']}:{conflict['event_b']}",
        conflict_description=description, proposed_new_time="next available free slot (not computed here)")


def evaluate(proposal: CalendarRescheduleProposal, plan_result: dict) -> CalendarRescheduleProposal:
    risks = ["Synthetic/no real Google Calendar connection - nothing is actually rescheduled by this proposal",
             "'next available free slot' is a placeholder - no real free/busy lookup exists in this fixture",
             "The choice of which event yields is an arbitrary heuristic, not the owner's real priority"]
    confidence = 0.3
    return CalendarRescheduleProposal(proposal.proposal_id, proposal.conflict_description,
                                      proposal.proposed_new_time, True, confidence, tuple(risks))


def make_proposal(path: Path) -> CalendarRescheduleProposal | None:
    conflict = load_synthetic(path)
    if conflict is None:
        return None
    plan_result = plan(conflict)
    draft = generate(plan_result, conflict)
    return evaluate(draft, plan_result)
