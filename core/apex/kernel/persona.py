"""Persona-card memory (Digital Twin extension, subsystem 2.E, 2026-11-15).

Two persona identities - e.g. an identity-preserving "owner" twin and a separate
female-presenting "companion" configuration - share the APEX fact store but must NOT
automatically share every memory. This module defines the persona-card record shape and
enforces, with a real PersonaIsolationError, which memories a given persona may read. It is
built on the EXISTING core/apex/kernel/facts.py (timestamped, sourced, append-only
assertions) - no new database, no new storage engine - following the identical philosophy
as core/apex/agents_governing.py's data-class isolation: deny by default, grant only what is
declared. It is not literally the same code, because a persona is not an agent role.

HONEST SCOPE: nothing in this module renders a face, synthesizes a voice, or drives an
avatar. It is exactly and only the record-keeping layer subsystem 2.E calls for.

HONEST LIMITATION, disclosed rather than hidden - read before storing anything sensitive
here: core/apex/kernel/memory.py's own module docstring already warns "Do not store
personal dossiers here" about this exact database file, because it is a plain local SQLite
file with no encryption at rest and (for the `events` table) an append-only hash chain with
NO deletion path at all - by design (events_no_update/events_no_delete triggers). facts.py's
table is a separate, non-hash-chained table in the SAME file, also append-only by convention
(nothing ever calls UPDATE/DELETE on it), so "deletion" of a persona memory in the sense of
true erasure is NOT implemented here and cannot be honestly faked: write_persona_card() and
remember() can always be followed by a NEW fact (a correction, or a later "superseded"
marker), but the prior row remains in the file. A real right-to-erasure capability would
need a SEPARATE store (e.g. an encrypted, non-append-only table, or an external KMS-backed
redaction mechanism) - a real design decision for the owner to make deliberately, not
something this module will pretend to provide with a UUID-named "delete" function that
doesn't actually delete anything.
"""
from __future__ import annotations

import json

from . import signing
from .facts import assert_fact, assert_signed_fact, fact_history, get_fact, query_fact, verify_fact_signature

SHARED, PRIVATE = "shared", "private"
_VISIBILITIES = frozenset({SHARED, PRIVATE})


class PersonaIsolationError(PermissionError):
    pass


_GRANTABLE_DATA_CLASSES = ("FINANCE", "MEDICAL")


def _card_signing_payload(persona_id, disclosure_text, voice_authorized, grants, version, prev_card_sig):
    grants_json = json.dumps(sorted(grants))
    return (persona_id, disclosure_text, voice_authorized, grants_json, version, prev_card_sig or "")


def write_persona_card(ledger, persona_id: str, display_name: str, presentation: str,
                       voice_authorized: bool, disclosure_text: str, created_by: str,
                       private_key_bytes: bytes, grants: list | None = None,
                       now: float | None = None) -> int:
    """Append-only: a persona card is never overwritten, only re-asserted - the full history
    of what a persona WAS configured as stays inspectable via persona_card_history(), the
    same discipline as every other claim in this kernel.

    HOLE CLOSED (brutal-honesty directive, 2026-11-15): grants used to live in a plain,
    unsigned JSON blob - anyone with DB write access could add 'MEDICAL' to a persona's
    grants without touching any fact's owner_sig, bypassing DATA_CLASS_DENIED entirely.
    Every card is now SIGNED: `private_key_bytes` is mandatory (supplied by the caller for
    this one call only - never read from or written to disk by this function), and the card
    carries its own `version` (1, 2, 3, ... per persona) and `prev_card_sig` (the previous
    version's own owner_sig, forming a chain of card versions so a revoke/grant history is
    itself auditable - distinct from facts.py's global prev_hash chain, which does not know
    anything about "this is a persona card" or "this supersedes that version"). The signed
    payload is (persona_id, disclosure_text, voice_authorized, grants_json, version,
    prev_card_sig) - grants included, so a grants-only edit invalidates the signature.

    disclosure_text is MANDATORY and non-empty: DPIF critical control 2 ("clear disclosure
    of synthetic identity") is enforced here structurally, not left to a UI convention that
    could be skipped. voice_authorized is a plain boolean attestation recorded by created_by
    - this module does not and cannot verify real-world consent; it only refuses to create a
    card that does not explicitly state whether voice use was authorized.

    `grants`: the sensitive data classes (FINANCE/MEDICAL) THIS persona is explicitly
    entitled to read from another persona's SHARED memories - empty by default. PUBLIC needs
    no grant. Granting is per-reading-persona, not per-fact."""
    if not isinstance(persona_id, str) or not persona_id.strip():
        raise ValueError("persona_id required")
    if not disclosure_text or not disclosure_text.strip():
        raise ValueError("disclosure_text is mandatory (DPIF critical control 2)")
    if type(voice_authorized) is not bool:
        raise ValueError("voice_authorized must be an explicit True/False attestation")
    if not isinstance(private_key_bytes, bytes) or len(private_key_bytes) != 32:
        raise ValueError("private_key_bytes must be 32 raw bytes")
    grants = [] if grants is None else list(grants)
    if any(g not in _GRANTABLE_DATA_CLASSES for g in grants):
        raise ValueError(f"grants must be a subset of {_GRANTABLE_DATA_CLASSES}")
    previous = read_persona_card(ledger, persona_id)
    version = 1 if previous is None else previous["version"] + 1
    prev_card_sig = None if previous is None else previous["owner_sig"]
    owner_sig = signing.sign_payload(private_key_bytes, *_card_signing_payload(
        persona_id, disclosure_text, voice_authorized, grants, version, prev_card_sig)).hex()
    card = {"persona_id": persona_id, "display_name": display_name, "presentation": presentation,
            "voice_authorized": voice_authorized, "disclosure_text": disclosure_text,
            "created_by": created_by, "grants": grants, "version": version,
            "owner_sig": owner_sig, "prev_card_sig": prev_card_sig}
    return assert_fact(ledger, f"persona:{persona_id}", "card", json.dumps(card),
                       f"persona_card:{created_by}", now=now)


def verify_persona_card(ledger, persona_id: str, public_key_bytes: bytes) -> bool:
    """Re-reads the CURRENT card (read_persona_card always returns the latest version by
    construction - there is no way to pass an old version into recall_fact, so "old version
    not current" is true by design, not by a special case here) and recomputes the signature
    over its CURRENT fields, grants included. Returns False - never raises - for: no card,
    a card written before signing was required (owner_sig/version/prev_card_sig missing), or
    any tampering of persona_id/disclosure_text/voice_authorized/grants/version/prev_card_sig."""
    card = read_persona_card(ledger, persona_id)
    if card is None:
        return False
    try:
        signature = bytes.fromhex(card["owner_sig"])
    except (KeyError, ValueError, TypeError):
        return False
    try:
        payload = _card_signing_payload(card["persona_id"], card["disclosure_text"], card["voice_authorized"],
                                        card["grants"], card["version"], card.get("prev_card_sig"))
    except KeyError:
        return False
    return signing.verify_payload(public_key_bytes, signature, *payload)


def read_persona_card(ledger, persona_id: str) -> dict | None:
    row = query_fact(ledger, f"persona:{persona_id}", "card")
    return None if row is None else json.loads(row["object"])


def persona_card_history(ledger, persona_id: str) -> list:
    return [{**h, "card": json.loads(h["object"])} for h in fact_history(ledger, f"persona:{persona_id}", "card")]


def remember(ledger, persona_id: str, memory_text: str, visibility: str, source: str,
            data_class: str = "PUBLIC", private_key_bytes: bytes | None = None,
            now: float | None = None) -> int:
    """A memory belongs to exactly one persona and is tagged shared-or-private AND a
    data_class AT WRITE TIME - never silently reclassified later. Raises
    PersonaIsolationError if no card has been written for this persona yet: a memory can
    never exist for an unconfigured persona, closing the "forgot to register the persona
    first" gap by construction.

    CRITICAL 2 (brutal-honesty directive, 2026-11-15): FINANCE/MEDICAL memories MUST be
    signed - facts.assert_fact() itself now refuses to write them unsigned
    (UnsignedFactError), so this function routes to facts.assert_signed_fact() and requires
    private_key_bytes whenever data_class is sensitive. PUBLIC memories are unaffected:
    data_class defaults to PUBLIC and no key is required, exactly as before."""
    if visibility not in _VISIBILITIES:
        raise ValueError("visibility must be 'shared' or 'private'")
    if read_persona_card(ledger, persona_id) is None:
        raise PersonaIsolationError(f"NO_PERSONA_CARD:{persona_id}")
    if data_class in _GRANTABLE_DATA_CLASSES:
        if private_key_bytes is None:
            raise ValueError(f"{data_class} memories must be signed - supply private_key_bytes "
                             "(CRITICAL 2, brutal-honesty directive 2026-11-15)")
        return assert_signed_fact(ledger, f"persona:{persona_id}", f"memory_{visibility}", memory_text,
                                  source, data_class, private_key_bytes, now=now)
    return assert_fact(ledger, f"persona:{persona_id}", f"memory_{visibility}", memory_text, source,
                       data_class=data_class, now=now)


def recall(*args, **kwargs):
    """DEPRECATED, REMOVED 2026-11-15 (brutal-honesty directive, GAP 2): this used to return
    a whole-history LIST and silently filter out anything the reading persona could not see
    - which made "access denied" indistinguishable from "nothing shared yet". That is exactly
    the ambiguity this entire module was built to avoid (recall_fact() raises instead). Use
    recall_fact() for a specific fact, or export_persona_memories() for a persona's own full
    history (no cross-persona filtering question there at all - it is always self-access).
    The name is kept, rather than deleted, specifically so calling it loudly fails instead of
    a caller accidentally resolving an old import to nothing."""
    raise NotImplementedError("use recall_fact; silent filter removed because it masked "
                              "access-denied as empty")


def recall_fact(ledger, reading_persona_id: str, fact_id: int, public_key_bytes: bytes | None = None) -> dict:
    """Per-fact isolation check: looks up ONE specific fact by id and raises
    PersonaIsolationError - never returns an empty/absent result - when the reading persona
    is not entitled to see it. A fact not shaped like a persona memory (wrong subject prefix
    or predicate) raises just as hard as a real cross-persona denial; there is no path that
    looks like "not found" when the real reason is "not allowed".

    A persona reading its OWN memory always succeeds, regardless of visibility or
    data_class - "FINANCE and MEDICAL stay with" the owning persona; they are not blocked
    from itself, only from others. For a CROSS-persona read, gates apply in order (GAP 1,
    brutal-honesty directive 2026-11-15): (1) the fact must be `shared`, and then, only if
    its data_class is FINANCE or MEDICAL: (2) the READING persona's own CARD must verify
    (verify_persona_card(), closing the HOLE where grants lived in unsigned data - `public_
    key_bytes` is required to reach this far; omitting it fails closed as unverified, never
    silently treated as "no grants to check"), and only then (3) the data_class must be
    present in that card's grants. PUBLIC needs no grant and no card verification at all."""
    if read_persona_card(ledger, reading_persona_id) is None:
        raise PersonaIsolationError(f"NO_PERSONA_CARD:{reading_persona_id}")
    fact = get_fact(ledger, fact_id)
    if fact is None or not fact["subject"].startswith("persona:") or not fact["predicate"].startswith("memory_"):
        raise PersonaIsolationError(f"NOT_A_PERSONA_MEMORY:{fact_id}")
    owning_persona_id = fact["subject"][len("persona:"):]
    visibility = fact["predicate"][len("memory_"):]
    if owning_persona_id == reading_persona_id:
        return fact                                   # self-access: never gated
    # Cross-persona read: GATE A (shared), then (for sensitive classes) card verification, then grant.
    if visibility != SHARED:
        raise PersonaIsolationError(f"NOT_SHARED:persona={owning_persona_id}:fact={fact_id}")
    if fact["data_class"] == "PUBLIC":
        return fact
    if fact["data_class"] in _GRANTABLE_DATA_CLASSES:
        # CRITICAL 2 (brutal-honesty directive, 2026-11-15): the FACT itself must be signed
        # before anything else is even checked - an unsigned FINANCE/MEDICAL row (which
        # assert_fact() now refuses to create, but a raw DB write could still produce) must
        # never be returned just because it happens to be shared and a grant exists.
        if public_key_bytes is None or not verify_fact_signature(ledger, fact_id, public_key_bytes):
            raise PersonaIsolationError(f"UNVERIFIED_FACT:fact={fact_id}")
        if not verify_persona_card(ledger, reading_persona_id, public_key_bytes):
            raise PersonaIsolationError(f"PERSONA_CARD_UNVERIFIED:persona={reading_persona_id}")
        reading_card = read_persona_card(ledger, reading_persona_id)
        if fact["data_class"] not in reading_card.get("grants", []):
            raise PersonaIsolationError(f"DATA_CLASS_DENIED:{fact['data_class']}:fact={fact_id}")
        return fact
    raise PersonaIsolationError(f"UNKNOWN_DATA_CLASS:{fact['data_class']}:fact={fact_id}")


def export_persona_memories(ledger, persona_id: str) -> dict:
    """Owner-controlled EXPORT (subsystem 2.E) - a real, read-only function. There is no
    matching import()/delete(): import would mean fabricating history for an append-only
    store, and true deletion is the explicitly disclosed limitation above."""
    card = read_persona_card(ledger, persona_id)
    if card is None:
        raise PersonaIsolationError(f"NO_PERSONA_CARD:{persona_id}")
    return {"persona_id": persona_id, "card": card, "card_history": persona_card_history(ledger, persona_id),
            "shared_memories": fact_history(ledger, f"persona:{persona_id}", f"memory_{SHARED}", limit=500),
            "private_memories": fact_history(ledger, f"persona:{persona_id}", f"memory_{PRIVATE}", limit=500)}
