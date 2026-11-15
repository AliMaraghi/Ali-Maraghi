"""Email domain (STAGED per core/apex/action_domains/router.ACTIVE_DOMAIN == BILLS). Planner/
generator/evaluator over a synthetic inbox-item JSON file. No IMAP/SMTP connection, no real
email access - built and tested so it is ready, not executed by agents_runner.py --once
while a different domain is active (see docs/FROZEN_SYSTEMS.md's distinction: staged is
in-scope-but-not-yet, frozen is explicitly out-of-scope).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = ("sender", "subject")


@dataclass(frozen=True)
class EmailDraftProposal:
    proposal_id: str
    sender: str
    subject: str
    draft_body: str
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


def plan(email: dict) -> dict:
    """Urgency heuristic over the subject line text only - no body content, no sender
    reputation data exists in this synthetic fixture."""
    urgent = "urgent" in email["subject"].lower() or "asap" in email["subject"].lower()
    return {"tone": "prompt" if urgent else "normal"}


def generate(plan_result: dict, email: dict) -> EmailDraftProposal:
    opener = "Thanks for flagging this - " if plan_result["tone"] == "prompt" else "Thanks for your message - "
    draft = f"{opener}I'll review \"{email['subject']}\" and get back to you shortly."
    return EmailDraftProposal(
        proposal_id=f"email:{email['sender']}:{email['subject'][:40]}",
        sender=email["sender"], subject=email["subject"], draft_body=draft)


def evaluate(proposal: EmailDraftProposal, plan_result: dict) -> EmailDraftProposal:
    risks = ["Synthetic/no real IMAP or SMTP connection - this draft cannot send anything by itself",
             "No sender verification - a spoofed or phished sender address would look identical here"]
    confidence = 0.5
    return EmailDraftProposal(proposal.proposal_id, proposal.sender, proposal.subject,
                              proposal.draft_body, True, confidence, tuple(risks))


def make_proposal(path: Path) -> EmailDraftProposal | None:
    email = load_synthetic(path)
    if email is None:
        return None
    plan_result = plan(email)
    draft = generate(plan_result, email)
    return evaluate(draft, plan_result)
