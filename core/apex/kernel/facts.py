"""Append-only fact store with provenance, built on the EXISTING Ledger - no new database, no
graph engine, no vector store. Each row is a dated, sourced assertion (subject, predicate,
object, source, asserted_at). Nothing is ever updated or deleted (same append-only discipline as
the rest of the Ledger); the "current value" of a (subject, predicate) pair is simply its most
recent assertion, and the full history stays queryable - this is the bi-temporal memory idea
done honestly in plain SQLite, not a promise of something heavier that was never built.

fact_outcomes is the second half: a place to record what actually happened after a fact/
recommendation was acted on (or not). Today nothing populates it automatically - that would mean
guessing the owner's intent from a voice utterance, which this project does not do. It exists so
scripts/record_outcome.py (a deliberate, explicit owner action) has somewhere real to write,
which is the actual prerequisite for any future calibration - there is none today, and no claim
of "learning" is made just because this table exists.
"""
from __future__ import annotations

import sqlite3
import time

from .engine import canonical
from .memory import Ledger as _LedgerForDigest   # reuse Ledger.digest() verbatim - see _chain_value
from . import signing

_OUTCOMES = frozenset({"accepted", "rejected", "acted_on", "ignored"})
_GENESIS = "0" * 64


def _ensure_facts_table(ledger):
    ledger.db.execute("""
        CREATE TABLE IF NOT EXISTS facts (
          id INTEGER PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
          object TEXT NOT NULL, source TEXT NOT NULL, asserted_at REAL NOT NULL,
          owner_sig TEXT, prev_hash TEXT)
    """)
    ledger.db.execute("CREATE INDEX IF NOT EXISTS facts_subject_predicate ON facts(subject, predicate, asserted_at DESC)")
    # Additive, idempotent migration for a facts table created before owner_sig/prev_hash
    # existed - CREATE TABLE IF NOT EXISTS above is a no-op on an existing table, so these
    # columns would otherwise never appear on it. "Already exists" is swallowed; anything
    # else is a real error and must surface.
    for column in ("owner_sig TEXT", "prev_hash TEXT"):
        try:
            ledger.db.execute(f"ALTER TABLE facts ADD COLUMN {column}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise


def _chain_value(fact_id, subject, predicate, obj, source, asserted_at, prev_hash) -> str:
    """The facts-table hash chain, reusing memory.py's Ledger.digest() VERBATIM (same
    staticmethod, same sha256(canonical([...])) pattern already proven for the events
    table) rather than a redesigned algorithm - just fed fact-shaped values instead of
    event-shaped ones. digest() performs no domain/kind validation of its own; it is a pure
    hash function over whatever five-plus-previous values it is given."""
    return _LedgerForDigest.digest(fact_id, f"{subject}|{predicate}", "fact", "fact",
                                   canonical([obj, source, asserted_at]), prev_hash)


def _ensure_outcomes_table(ledger):
    ledger.db.execute("""
        CREATE TABLE IF NOT EXISTS fact_outcomes (
          id INTEGER PRIMARY KEY, fact_id INTEGER NOT NULL, outcome TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '', recorded_at REAL NOT NULL)
    """)


def _nonempty_str(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def assert_fact(ledger, subject: str, predicate: str, obj: str, source: str, now: float | None = None) -> int:
    _nonempty_str(subject, "subject"), _nonempty_str(predicate, "predicate")
    _nonempty_str(obj, "object"), _nonempty_str(source, "source")
    _ensure_facts_table(ledger)
    now = time.time() if now is None else now
    cur = ledger.db.execute(
        "INSERT INTO facts (subject, predicate, object, source, asserted_at) VALUES (?,?,?,?,?)",
        (subject, predicate, obj, source, now))
    return cur.lastrowid


def get_fact(ledger, fact_id: int) -> dict | None:
    """Direct lookup by id - the primitive persona.recall_fact() needs to check isolation
    against a SPECIFIC fact rather than scanning a whole history list."""
    _ensure_facts_table(ledger)
    row = ledger.db.execute(
        "SELECT subject, predicate, object, source, asserted_at FROM facts WHERE id=?", (fact_id,)).fetchone()
    if row is None:
        return None
    return {"id": fact_id, "subject": row[0], "predicate": row[1], "object": row[2], "source": row[3], "asserted_at": row[4]}


def query_fact(ledger, subject: str, predicate: str) -> dict | None:
    """The CURRENT value: the most recent assertion, or None if nothing was ever asserted."""
    _ensure_facts_table(ledger)
    row = ledger.db.execute(
        "SELECT id, object, source, asserted_at FROM facts WHERE subject=? AND predicate=? "
        "ORDER BY asserted_at DESC, id DESC LIMIT 1", (subject, predicate)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "subject": subject, "predicate": predicate, "object": row[1], "source": row[2], "asserted_at": row[3]}


def fact_history(ledger, subject: str, predicate: str, limit: int = 50) -> list:
    """Every assertion ever made for this (subject, predicate), newest first - nothing is ever
    overwritten or hidden, so a contradiction shows up as two rows, not a silent correction."""
    _ensure_facts_table(ledger)
    if not 1 <= limit <= 500:
        raise ValueError("limit out of bounds")
    rows = ledger.db.execute(
        "SELECT id, object, source, asserted_at FROM facts WHERE subject=? AND predicate=? "
        "ORDER BY asserted_at DESC, id DESC LIMIT ?", (subject, predicate, limit)).fetchall()
    return [{"id": r[0], "subject": subject, "predicate": predicate, "object": r[1], "source": r[2], "asserted_at": r[3]} for r in rows]


def assert_signed_fact(ledger, subject: str, predicate: str, obj: str, source: str,
                       private_key_bytes: bytes, now: float | None = None) -> int:
    """Opt-in signed variant of assert_fact() - no existing caller of assert_fact() is
    affected; owner_sig/prev_hash stay NULL on every unsigned fact exactly as before.

    Ordering, made explicit per the brutal-honesty directive's Amendment 3: the timestamp is
    finalized FIRST (`now` resolved to a concrete float before anything else runs), then the
    hash-chain link is read, THEN the signature is computed over the now-fixed tuple
    (subject, predicate, obj, source, asserted_at, prev_hash), and only then is the row
    inserted. Signing over a value that could still change after the fact would make the
    signature meaningless; this function cannot do that by construction.

    `private_key_bytes` is supplied by the CALLER for this one call only. This function
    never reads a key from disk, never writes one to disk, and never logs one - the real
    owner key, if this is ever wired into a real deployment, lives only on the personal
    machine and is handed in by whatever process already holds it."""
    _nonempty_str(subject, "subject"), _nonempty_str(predicate, "predicate")
    _nonempty_str(obj, "object"), _nonempty_str(source, "source")
    if not isinstance(private_key_bytes, bytes) or len(private_key_bytes) != 32:
        raise ValueError("private_key_bytes must be 32 raw bytes")
    _ensure_facts_table(ledger)
    asserted_at = time.time() if now is None else now          # finalized before anything else
    with ledger.transaction():
        # The chain links SIGNED facts to each other only (an interleaved unsigned
        # assert_fact() call carries no chain link at all - see verify_fact_chain's
        # matching skip-unsigned behaviour below); this keeps the two in agreement.
        last_signed = ledger.db.execute(
            "SELECT id, subject, predicate, object, source, asserted_at, prev_hash "
            "FROM facts WHERE owner_sig IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = _GENESIS if last_signed is None else _chain_value(*last_signed)
        owner_sig = signing.sign_payload(private_key_bytes, subject, predicate, obj, source,
                                         asserted_at, prev_hash).hex()
        cur = ledger.db.execute(
            "INSERT INTO facts (subject, predicate, object, source, asserted_at, owner_sig, prev_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (subject, predicate, obj, source, asserted_at, owner_sig, prev_hash))
        return cur.lastrowid


def verify_fact_signature(ledger, fact_id: int, public_key_bytes: bytes) -> bool:
    """Re-queries the CURRENT row from the database (Amendment 3: not a cached value from
    assertion time), recomputes the signature payload over the row's current
    (subject, predicate, obj, source, asserted_at, prev_hash), and compares to the stored
    owner_sig. Returns False - never raises, never "unverifiable" - for: no such fact, an
    unsigned fact (owner_sig is NULL), or any tampering of any one of those six fields."""
    _ensure_facts_table(ledger)
    row = ledger.db.execute(
        "SELECT subject, predicate, object, source, asserted_at, owner_sig, prev_hash "
        "FROM facts WHERE id=?", (fact_id,)).fetchone()
    if row is None or row[5] is None:
        return False
    subject, predicate, obj, source, asserted_at, owner_sig, prev_hash = row
    try:
        signature = bytes.fromhex(owner_sig)
    except ValueError:
        return False
    return signing.verify_payload(public_key_bytes, signature, subject, predicate, obj,
                                  source, asserted_at, prev_hash)


def verify_fact_chain(ledger) -> dict:
    """The facts-table counterpart to Ledger.audit_chain() (Phase 4): an O(n) walk from
    genesis that NEVER raises, returning {"ok","length","first_broken_id","reason"} - the
    first broken id, not a boolean. Detects an in-place edit (DIGEST_MISMATCH via the next
    row's prev_hash no longer matching), a deleted row (GAP, since the deletion removes the
    link the next row's prev_hash depended on) and reordering (PREV_HASH_MISMATCH)."""
    expected_prev, length = _GENESIS, 0
    rows = ledger.db.execute(
        "SELECT id, subject, predicate, object, source, asserted_at, prev_hash "
        "FROM facts ORDER BY id").fetchall()
    for row in rows:
        fact_id, subject, predicate, obj, source, asserted_at, prev_hash = row
        if prev_hash is None:
            continue                     # an unsigned fact carries no chain link - skipped, not a break
        if prev_hash != expected_prev:
            return {"ok": False, "length": length, "first_broken_id": fact_id, "reason": "PREV_HASH_MISMATCH"}
        expected_prev = _chain_value(*row)
        length += 1
    return {"ok": True, "length": length, "first_broken_id": None, "reason": None}


def record_outcome(ledger, fact_id: int, outcome: str, note: str = "", now: float | None = None) -> int:
    if outcome not in _OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(_OUTCOMES)}")
    if type(fact_id) is not int or fact_id <= 0:
        raise ValueError("fact_id must be a positive integer")
    if len(note) > 500:
        raise ValueError("note too long")
    _ensure_outcomes_table(ledger)
    now = time.time() if now is None else now
    cur = ledger.db.execute(
        "INSERT INTO fact_outcomes (fact_id, outcome, note, recorded_at) VALUES (?,?,?,?)",
        (fact_id, outcome, note, now))
    return cur.lastrowid


def outcomes_for(ledger, fact_id: int) -> list:
    _ensure_outcomes_table(ledger)
    rows = ledger.db.execute(
        "SELECT outcome, note, recorded_at FROM fact_outcomes WHERE fact_id=? ORDER BY recorded_at DESC", (fact_id,)).fetchall()
    return [{"outcome": r[0], "note": r[1], "recorded_at": r[2]} for r in rows]


def recent_outcomes_for_predicate_prefix(ledger, subject: str, predicate_prefix: str, limit: int = 5) -> list:
    """The actual calibration hook: every fact whose predicate starts with `predicate_prefix`
    (e.g. "finance_claim_") that has a recorded outcome, newest first. This is what lets a
    caller change behavior because of what genuinely happened before - not a promise, a real
    join against fact_outcomes."""
    _ensure_facts_table(ledger)
    _ensure_outcomes_table(ledger)
    if not 1 <= limit <= 50:
        raise ValueError("limit out of bounds")
    rows = ledger.db.execute(
        "SELECT f.object, o.outcome, o.note, o.recorded_at FROM fact_outcomes o "
        "JOIN facts f ON f.id = o.fact_id "
        "WHERE f.subject=? AND f.predicate LIKE ? ESCAPE '\\' "
        "ORDER BY o.recorded_at DESC LIMIT ?",
        (subject, predicate_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", limit)).fetchall()
    return [{"claim_text": r[0], "outcome": r[1], "note": r[2], "recorded_at": r[3]} for r in rows]


def find_contradictions(ledger, limit: int = 100) -> list:
    """Every (subject, predicate) pair with more than one DISTINCT asserted value - a genuine
    contradiction (two different claims about the same thing), not just the same value re-
    asserted. A read-only scan of the existing facts table; nothing here is inferred, resolved,
    or silently picked as "the real one" - that judgement call stays with whoever reads this."""
    _ensure_facts_table(ledger)
    if not 1 <= limit <= 1000:
        raise ValueError("limit out of bounds")
    pairs = ledger.db.execute(
        "SELECT subject, predicate, COUNT(DISTINCT object) AS n FROM facts "
        "GROUP BY subject, predicate HAVING n > 1 ORDER BY subject, predicate LIMIT ?", (limit,)).fetchall()
    return [{"subject": subject, "predicate": predicate,
             "history": fact_history(ledger, subject, predicate, limit=50)}
            for subject, predicate, _n in pairs]
