"""Applies an evolution proposal AFTER the owner approved it in the console. Never before.

For each `evolution-promote` proposal in state APPROVED that has not been applied yet:
  1. rebuild the candidate from the approved payload (only the EVOLVE-BLOCK text is taken from
     it; everything outside the markers comes from the file on disk);
  2. check the stored payload still matches the hash the owner approved;
  3. run the static guard again and re-score it - it must still not be worse than the baseline;
  4. write target_heuristics.py, run the caller's test command, and put the old file back if
     the tests fail.
The caller (scripts/apply_evolution.py) commits the file; the push to GitHub is a separate,
privacy-scanned step. Each outcome is written to evolution_log.
"""
from __future__ import annotations

import json
import time
from typing import Callable

from ..kernel.approvals import payload_hash
from . import config, evaluator, guard

KIND = "evolution-promote"


def _ensure(db) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS evolution_applied (proposal_id TEXT PRIMARY KEY, applied_at REAL NOT NULL, outcome TEXT NOT NULL)")


def pending_approved(ledger) -> list[str]:
    _ensure(ledger.db)
    if not ledger.db.execute("SELECT 1 FROM sqlite_master WHERE name='proposals'").fetchone():
        return []
    return [r[0] for r in ledger.db.execute(
        "SELECT id FROM proposals WHERE kind=? AND state='APPROVED' AND id NOT IN (SELECT proposal_id FROM evolution_applied) "
        "ORDER BY created_at", (KIND,))]


def apply_one(ledger, proposal_id: str, run_tests: Callable[[], bool], now: float | None = None) -> str:
    """Returns the outcome: APPLIED, or a REFUSED_* / REVERTED_* reason. Idempotent per proposal."""
    now = time.time() if now is None else now
    _ensure(ledger.db)
    outcome = _apply(ledger, proposal_id, run_tests)
    ledger.db.execute("INSERT OR REPLACE INTO evolution_applied VALUES (?,?,?)", (proposal_id, now, outcome))
    ledger.db.execute(
        "CREATE TABLE IF NOT EXISTS evolution_log (id INTEGER PRIMARY KEY, recorded_at REAL NOT NULL, generation TEXT NOT NULL, "
        "baseline_score REAL, candidate_score REAL, examples INTEGER NOT NULL, safety_violations INTEGER NOT NULL, "
        "decision TEXT NOT NULL, detail TEXT NOT NULL)")
    ledger.db.execute("INSERT INTO evolution_log (recorded_at, generation, baseline_score, candidate_score, examples, "
                      "safety_violations, decision, detail) VALUES (?,?,NULL,NULL,0,0,?,?)",
                      (now, "apply", outcome, proposal_id))
    return outcome


def _apply(ledger, proposal_id: str, run_tests: Callable[[], bool]) -> str:
    if not config.enabled():
        return "REFUSED_DISABLED"
    row = ledger.db.execute("SELECT kind, state, payload, payload_hash FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if row is None or row[0] != KIND or row[1] != "APPROVED":
        return "REFUSED_NOT_APPROVED"
    try:
        body = json.loads(row[2])
    except ValueError:
        return "REFUSED_UNREADABLE"
    if payload_hash(body) != row[3]:
        return "REFUSED_TAMPERED"
    block = body.get("payload", {}).get("block")
    if not isinstance(block, str):
        return "REFUSED_NO_BLOCK"
    baseline = evaluator.BASELINE.read_text(encoding="utf-8")
    head, _, tail = guard.split(baseline)
    candidate = head + guard.START + block + guard.END + tail
    if candidate == baseline:
        return "REFUSED_NO_CHANGE"
    if guard.violations(baseline, candidate):
        return "REFUSED_UNSAFE"
    examples, _mode = evaluator.select_benchmark(ledger, int(config.load()["min_real_outcomes"]))
    evaluator.BASELINE.write_text(candidate, encoding="utf-8")
    try:
        new = evaluator.evaluate_source(candidate, str(evaluator.BASELINE), examples)
        evaluator.BASELINE.write_text(baseline, encoding="utf-8")
        old = evaluator.evaluate_source(baseline, str(evaluator.BASELINE), examples)
        if new.get("status") != "SCORED" or new["combined_score"] < old.get("combined_score", 0.0):
            return "REFUSED_NO_LONGER_BETTER"
        evaluator.BASELINE.write_text(candidate, encoding="utf-8")
        if not run_tests():
            evaluator.BASELINE.write_text(baseline, encoding="utf-8")
            return "REVERTED_TESTS_FAILED"
    except Exception:
        evaluator.BASELINE.write_text(baseline, encoding="utf-8")
        return "REVERTED_ERROR"
    return "APPLIED"
