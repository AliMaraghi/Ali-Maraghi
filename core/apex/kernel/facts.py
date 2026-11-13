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

import time

_OUTCOMES = frozenset({"accepted", "rejected", "acted_on", "ignored"})


def _ensure_facts_table(ledger):
    ledger.db.execute("""
        CREATE TABLE IF NOT EXISTS facts (
          id INTEGER PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
          object TEXT NOT NULL, source TEXT NOT NULL, asserted_at REAL NOT NULL)
    """)
    ledger.db.execute("CREATE INDEX IF NOT EXISTS facts_subject_predicate ON facts(subject, predicate, asserted_at DESC)")


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
