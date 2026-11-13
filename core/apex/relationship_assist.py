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
