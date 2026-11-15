"""Relationship / dating ASSISTANCE: owner-provided notes and manual drafts only. Status: TESTS_NOT_RUN.

Boundary from the specification and platform policy: this module has NO account access, NO network, NO
messaging and NO browser control. It cannot swipe, send, impersonate or collect cookies/sessions. Every draft
is a package for the owner to review and send by hand. Photos are never processed here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN = re.compile(
    r"\b(auto[- ]?(swipe|reply|message|chat|like)|swipe for me|send (it|this|messages?) (for me|automatically)|"
    r"impersonat\w*|pretend to be|fake (profile|identity)|cookie|session token|bypass|captcha|anti[- ]?bot|"
    r"scrape|log ?in (for|as) me)\b", re.I)
MAX_NOTE = 4000
MAX_DRAFT_CONTEXT = 2000
TONES = ("warm", "playful", "direct", "calm")


class AssistRefused(PermissionError):
    pass


@dataclass(frozen=True)
class Note:
    person_label: str          # owner-chosen label, never a platform account id
    text: str
    created: str               # caller supplies an ISO date; this module reads no clock


@dataclass(frozen=True)
class DraftPackage:
    purpose: str
    tone: str
    context: str
    guidance: tuple[str, ...]
    send: bool = False         # always False: drafts are never sent by software
    requires_owner_review: bool = True


def guard(text: str) -> None:
    """Refuse requests for automation, impersonation or access-token handling."""
    if FORBIDDEN.search(text or ""):
        raise AssistRefused("Automation, impersonation, session handling and anti-bot bypass are not supported; "
                            "a manual draft or note can be prepared instead")


def make_note(person_label: str, text: str, created: str) -> Note:
    guard(text)
    if not person_label.strip() or not 0 < len(text) <= MAX_NOTE:
        raise ValueError("Note needs a label and 1-4000 characters")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", created):
        raise ValueError("created must be YYYY-MM-DD")
    return Note(person_label.strip()[:80], text.strip(), created)


def draft_package(purpose: str, context: str, tone: str = "warm") -> DraftPackage:
    guard(purpose)
    guard(context)
    if tone not in TONES:
        raise ValueError("tone must be one of " + ", ".join(TONES))
    if not purpose.strip() or not 0 < len(context) <= MAX_DRAFT_CONTEXT:
        raise ValueError("purpose and bounded context required")
    return DraftPackage(
        purpose=purpose.strip()[:200], tone=tone, context=context.strip(),
        guidance=("Write in the owner's own voice and say nothing untrue about the owner.",
                  "Be respectful; honour any stated boundary or preference in the notes.",
                  "No pressure, manipulation or hidden persuasion; do not imply a relationship that does not exist.",
                  "The owner reviews and sends manually; this package is never transmitted by software."))


LADDER_STAGES = ("opener", "discovery", "banter", "date_invite")
_LADDER_PURPOSE = {
    "opener": "a first message that references something specific and real in their profile - never a generic compliment",
    "discovery": "a question that invites them to share something about themselves - never a compliment disguised as a question",
    "banter": "a light, playful reply that builds on something they already said - never a new, unrelated topic",
    "date_invite": "a specific invitation naming where, roughly when, and roughly how long - never a vague 'we should hang out sometime'",
}


def ladder_message(stage: str, context: str, tone: str = "warm") -> DraftPackage:
    """One stage of a conversation (A-10 London extension): opener -> discovery -> banter ->
    date_invite. Each stage is a draft_package() call with a stage-specific purpose, so it
    inherits guard()'s automation/impersonation refusal and every other DraftPackage field
    (requires_owner_review=True, send=False) unchanged - this function adds no new capability,
    only a fixed vocabulary of purposes for the four real stages a conversation goes through."""
    if stage not in LADDER_STAGES:
        raise ValueError(f"stage must be one of {LADDER_STAGES}")
    return draft_package(_LADDER_PURPOSE[stage], context, tone)


def record_post_date_feedback(ledger, person_label: str, what_worked: str, what_didnt: str,
                              next_time: str, now=None) -> int:
    """Post-date feedback loop (A-10 London extension): three real questions, recorded as an
    append-only fact under this person's own label - the same facts store
    (core/apex/kernel/facts.py) every other calibration loop in this project uses, so
    recent_outcomes_for_predicate_prefix() and this project's existing calibration pattern
    apply here without any new mechanism. guard() applies to all three fields - a feedback
    note cannot itself contain an automation/impersonation request any more than a draft can."""
    for text in (what_worked, what_didnt, next_time):
        guard(text)
    from .kernel import facts as factstore
    summary = f"worked: {what_worked.strip()[:300]} | did not work: {what_didnt.strip()[:300]} | next time: {next_time.strip()[:300]}"
    return factstore.assert_fact(ledger, f"relationship:{person_label}", "post_date_feedback", summary, "owner", now=now)


def weekly_review(messages_sent: int, replies_received: int, dates_booked: int) -> dict:
    """Weekly review (A-10 London extension): two real ratios, two real thresholds, named
    exactly as specified - a reply rate below 10% flags the MESSAGES as the likely problem;
    a date rate (of replies) below 20% flags the INVITATIONS as the likely problem. Pure
    arithmetic over owner-supplied counts - this function reads no ledger and infers no
    intent; the caller supplies real counts from their own real week."""
    for value, name in ((messages_sent, "messages_sent"), (replies_received, "replies_received"),
                        (dates_booked, "dates_booked")):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if replies_received > messages_sent:
        raise ValueError("replies_received cannot exceed messages_sent")
    if dates_booked > replies_received:
        raise ValueError("dates_booked cannot exceed replies_received")
    reply_rate = replies_received / messages_sent if messages_sent else 0.0
    date_rate = dates_booked / replies_received if replies_received else 0.0
    issues = []
    if messages_sent > 0 and reply_rate < 0.10:
        issues.append("reply_rate_below_10pct: the messages likely have a problem")
    if replies_received > 0 and date_rate < 0.20:
        issues.append("date_rate_below_20pct: the invitations likely have a problem")
    return {"messages_sent": messages_sent, "replies_received": replies_received, "dates_booked": dates_booked,
            "reply_rate": reply_rate, "date_rate": date_rate, "issues": issues}


def bio_checklist(bio: str) -> list[str]:
    """Rule-based, non-judgemental prompts for the owner; no scoring and no model call."""
    guard(bio)
    out = []
    if len(bio) < 60:
        out.append("The bio is very short; consider adding one specific interest or detail.")
    if len(bio) > 500:
        out.append("The bio is long; consider keeping the key points near the start.")
    if not re.search(r"[.!?]", bio):
        out.append("No sentence punctuation found; read it aloud to check the tone.")
    if re.search(r"\b(looking for someone who|no drama)\b", bio, re.I):
        out.append("Consider phrasing preferences positively (what you enjoy) rather than as exclusions.")
    return out or ["No mechanical issues found; review the tone yourself."]
