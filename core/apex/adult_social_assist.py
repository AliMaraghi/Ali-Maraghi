"""Adult social/dating assistance (consenting-adults, opt-in platforms) - owner-provided
notes and manual drafts only. Status: TESTS_NOT_RUN until this module's own tests run.

Same boundary as relationship_assist.py, explicitly restated for this higher-stakes case:
NO account access, NO network, NO messaging, NO browser control, NO scraping, NO fake
accounts, NO bots. Every draft is a package the owner reviews and sends by hand, one person
at a time, based on that person's own real profile. Nothing here fabricates the owner's own
identity, age, appearance, experience or real photos - those are owner-only inputs this
module takes as parameters, never invents. Per the mission's own explicit instruction, this
account (work) does not hold or request the owner's real identity/photo data; the owner
supplies it locally at use time (e.g. on the personal machine) if this module runs there.

Consent and safety are structural, not advisory text: etiquette_guard() rejects the specific
abusive patterns the mission names (mass copy-paste, content-free openers, an explicit image
in a first message, pressure for an immediate meetup, continuing after "no", messaging someone
whose stated profile does not match what the owner is looking for) before a draft is ever
produced, and record_safety_checklist() makes the pre-date checklist a persisted fact, not a
reminder that can be silently skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .relationship_assist import AssistRefused, DraftPackage, guard

PLATFORMS = ("fabswingers", "feeld", "fetlife", "sdc")

_GENERIC_OPENER = re.compile(r"^\s*((hi|hey|hello|yo)[.!? ]*(u up\??)?|u ?up\??)\s*$", re.I)
_IMMEDIATE_PRESSURE = re.compile(
    r"\b(meet (tonight|right now|now)|come over now|tonight\?|let'?s meet up tonight)\b", re.I)
MAX_FIRST_MESSAGE_SENTENCES = 4


class EtiquetteRefused(AssistRefused):
    pass


@dataclass(frozen=True)
class PlatformProfile:
    platform: str
    rationale: str
    fields: tuple[str, ...]      # structural field names only - no owner data filled in here


def platform_profile_template(platform: str) -> PlatformProfile:
    """Structural template per platform, S1. This returns FIELD NAMES and per-platform
    rationale only - the owner's real age/area/appearance/experience/DDF status/limits must
    be supplied by the owner at use time; this module does not invent or store them."""
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {PLATFORMS}")
    templates = {
        "fabswingers": PlatformProfile(
            platform="fabswingers",
            rationale="Direct, explicit-is-expected culture: role, age, area, DDF and what/what-not "
                       "upfront reduce mismatched contact rather than create it.",
            fields=("role_self_description", "age", "london_area", "appearance", "experience_level",
                    "ddf_status", "seeking", "not_seeking", "consent_statement")),
        "feeld": PlatformProfile(
            platform="feeld",
            rationale="Desires-field-first UI rewards a complete, specific desires list over a long bio; "
                       "photo verification is enforced by the platform itself.",
            fields=("short_bio", "desires_tags", "age", "london_area", "ddf_status", "seeking",
                    "not_seeking", "consent_statement", "photo_verified")),
        "fetlife": PlatformProfile(
            platform="fetlife",
            rationale="Kink-literate audience: experience and HARD LIMITS stated plainly are read as "
                       "competence and respect, not oversharing.",
            fields=("bdsm_experience", "interests", "hard_limits", "age", "london_area",
                    "ddf_status", "consent_statement")),
        "sdc": PlatformProfile(
            platform="sdc",
            rationale="International lifestyle audience with an events focus: a fuller profile plus "
                       "named London events signals genuine local intent over a drive-by account.",
            fields=("full_bio", "age", "london_area", "appearance", "experience_level", "ddf_status",
                    "seeking", "not_seeking", "consent_statement", "london_events_interested_in")),
    }
    return templates[platform]


def draft_first_message(their_profile_detail: str, owner_intro: str, question: str, tone: str = "warm",
                         includes_explicit_image: bool = False) -> DraftPackage:
    """S2: a first-message draft referencing something specific and real in the other
    person's own stated profile. Hard-capped at 4 sentences total, never includes an explicit
    image (the mission's own rule - raises before drafting if the caller tries), never
    pressures for an immediate meetup."""
    if includes_explicit_image:
        raise EtiquetteRefused("No explicit image in a first message - not supported")
    guard(their_profile_detail)
    guard(owner_intro)
    guard(question)
    if not their_profile_detail.strip():
        raise ValueError("their_profile_detail must reference something specific and real")
    full_text = f"{owner_intro.strip()} {question.strip()}".strip()
    etiquette_guard(full_text)
    sentence_count = len([s for s in re.split(r"[.!?]+", full_text) if s.strip()])
    if sentence_count > MAX_FIRST_MESSAGE_SENTENCES:
        raise ValueError(f"first message must be at most {MAX_FIRST_MESSAGE_SENTENCES} sentences, got {sentence_count}")
    context = f"their profile detail referenced: {their_profile_detail.strip()[:300]}"
    return DraftPackage(
        purpose="a first message referencing something specific and real in their profile, "
                "introducing the owner in 2-3 sentences, with one easy question - no explicit "
                "image, no pressure for an immediate meetup",
        tone=tone, context=context,
        guidance=("Reference the specific detail named, not a generic compliment.",
                  "State the owner's own real age/appearance/experience/DDF honestly - never fabricated.",
                  "No explicit image in this message. No pressure for an immediate meetup.",
                  "The owner reviews and sends manually; one message, one person, based on their real profile."))


def etiquette_guard(message_text: str, *, is_duplicate_of_others: bool = False,
                     includes_explicit_image: bool = False, after_a_no: bool = False,
                     profile_mismatch: bool = False) -> None:
    """S4: reject the 6 named patterns before a draft ever reaches the agent. Each parameter
    is information the OWNER (or the calling code tracking conversation history) supplies -
    this function does not infer duplication or mismatch from text alone."""
    if is_duplicate_of_others:
        raise EtiquetteRefused("Identical copy-paste to multiple people is not supported")
    if _GENERIC_OPENER.match(message_text or ""):
        raise EtiquetteRefused('Content-free openers ("Hi", "Hey", "U up?") are not supported')
    if includes_explicit_image:
        raise EtiquetteRefused("No explicit image in a first message - not supported")
    if _IMMEDIATE_PRESSURE.search(message_text or ""):
        raise EtiquetteRefused("Pressure for an immediate meetup is not supported")
    if after_a_no:
        raise EtiquetteRefused('No further message after a "no" - not supported')
    if profile_mismatch:
        raise EtiquetteRefused("Messaging someone whose stated profile does not match what the owner "
                               "is looking for is not supported")
    guard(message_text)


_INTEREST_WORDS = re.compile(r"\b(yes|sure|sounds? (good|great|fun)|would love|interested|let'?s|definitely)\b", re.I)
_COLD_WORDS = re.compile(r"\b(no( thanks)?|not interested|pass|not for me)\b", re.I)


def classify_response(response_text: str) -> str:
    """S3 triage: 'interested' / 'neutral' / 'cold', used to pick the next draft stage."""
    text = (response_text or "").strip()
    if not text:
        return "neutral"
    if _COLD_WORDS.search(text):
        return "cold"
    if _INTEREST_WORDS.search(text):
        return "interested"
    return "neutral"


def next_step_for(classification: str) -> str:
    if classification == "cold":
        return "close_respectfully"
    if classification == "interested":
        return "propose_public_meetup"
    if classification == "neutral":
        return "ask_a_discovery_question"
    raise ValueError("classification must be 'interested', 'neutral' or 'cold'")


SAFETY_CHECKLIST_ITEMS = (
    "full_address_known_and_shared_with_a_friend",
    "own_recent_sti_test_status_known",
    "safeword_agreed_if_bdsm",
    "no_photo_without_written_consent",
    "no_means_no_no_argument",
    "can_leave_without_explanation",
)


def record_safety_checklist(ledger, person_label: str, confirmed: dict, now=None) -> int:
    """S5: the pre-date checklist as a persisted fact, not just advisory text - every item
    must be explicitly confirmed True/False by the owner before this records a complete
    checklist; raises if any item is missing."""
    missing = [item for item in SAFETY_CHECKLIST_ITEMS if item not in confirmed]
    if missing:
        raise ValueError(f"missing checklist items: {missing}")
    from .kernel import facts as factstore
    summary = "; ".join(f"{item}={confirmed[item]}" for item in SAFETY_CHECKLIST_ITEMS)
    return factstore.assert_fact(ledger, f"adult_social:{person_label}", "pre_date_safety_checklist",
                                 summary, "owner", now=now)
