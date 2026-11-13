"""Bitemporal fact store on the local Ledger database. Status: TESTS_NOT_RUN.

Every fact has VALID time (when it was true in the world) and RECORDED time (when the system learned it).
Rows are immutable versions: corrections and endings add a new version of the same fact; nothing is updated
or deleted (database triggers abort both). Historical questions are answered "as of" a valid time and a
known-at time, so a later correction never rewrites what the system believed earlier. Evidence is mandatory.
Do not store level-4 personal data here: this is the VPS-side ledger, not the owner's local vault.
"""
from __future__ import annotations

import json
import time
import uuid

from .engine import canonical
from .schema import DOMAINS, identifier, strict_json

MAX_VALUE_BYTES = 8192


class TemporalError(ValueError):
    pass


class FactStore:
    def __init__(self, ledger, clock=time.time):
        self.ledger, self.clock = ledger, clock
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS fact_versions (
              fact_id TEXT NOT NULL, version INTEGER NOT NULL, domain TEXT NOT NULL,
              subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL,
              valid_from REAL NOT NULL, valid_to REAL, recorded_at REAL NOT NULL,
              evidence TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(fact_id, version));
            CREATE INDEX IF NOT EXISTS fact_lookup ON fact_versions(domain, subject, predicate);
            CREATE TRIGGER IF NOT EXISTS fact_versions_no_update BEFORE UPDATE ON fact_versions
              BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS fact_versions_no_delete BEFORE DELETE ON fact_versions
              BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        """)

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _check(domain, subject, predicate, evidence):
        if domain not in DOMAINS:
            raise TemporalError("Unknown domain")
        identifier(subject), identifier(predicate)
        if not evidence or not all(isinstance(e, str) and e for e in evidence):
            raise TemporalError("Evidence required")

    @staticmethod
    def _encode(value):
        encoded = canonical(value)
        if len(encoded.encode()) > MAX_VALUE_BYTES:
            raise TemporalError("Value too large")
        return encoded

    def _latest(self, fact_id, known_at=None):
        known = self.clock() if known_at is None else known_at
        return self.ledger.db.execute(
            "SELECT version,domain,subject,predicate,value,valid_from,valid_to,evidence FROM fact_versions "
            "WHERE fact_id=? AND recorded_at<=? ORDER BY version DESC LIMIT 1", (fact_id, known)).fetchone()

    def _write(self, fact_id, version, domain, subject, predicate, value, valid_from, valid_to, evidence, reason, now):
        self.ledger.db.execute("INSERT INTO fact_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (fact_id, version, domain, subject, predicate, value, valid_from, valid_to, now,
                                json.dumps(sorted(evidence)), reason))
        self.ledger._append(identifier(f"fact.{fact_id}.{version}"[:80]), "decision", domain,
                            {"event": "fact_" + reason, "fact": fact_id, "version": version})

    # ---- writes ------------------------------------------------------------
    def assert_fact(self, domain, subject, predicate, value, valid_from, evidence):
        """Record that `value` holds from `valid_from`; ends any open fact for the same subject/predicate then."""
        self._check(domain, subject, predicate, evidence)
        encoded = self._encode(value)
        now = self.clock()
        fact_id = "f" + uuid.uuid4().hex[:20]
        with self.ledger.transaction():
            for (open_id,) in self.ledger.db.execute(
                    "SELECT DISTINCT fact_id FROM fact_versions WHERE domain=? AND subject=? AND predicate=?",
                    (domain, subject, predicate)).fetchall():
                prev = self._latest(open_id, now)
                if prev and prev[6] is None:
                    if valid_from <= prev[5]:
                        raise TemporalError("New fact must start after the open fact; use correct() to amend it")
                    self._write(open_id, prev[0] + 1, domain, subject, predicate, prev[4], prev[5], valid_from,
                                json.loads(prev[7]), "superseded", now)
            self._write(fact_id, 1, domain, subject, predicate, encoded, valid_from, None, evidence, "asserted", now)
        return fact_id

    def correct(self, fact_id, new_value, evidence):
        """Amend what was believed about the same valid period; the previous belief stays queryable by known_at."""
        if not evidence:
            raise TemporalError("Evidence required")
        encoded, now = self._encode(new_value), self.clock()
        with self.ledger.transaction():
            prev = self._latest(fact_id, now)
            if prev is None:
                raise TemporalError("Unknown fact")
            self._write(fact_id, prev[0] + 1, prev[1], prev[2], prev[3], encoded, prev[5], prev[6], evidence, "corrected", now)

    def end_fact(self, fact_id, valid_to, evidence):
        now = self.clock()
        with self.ledger.transaction():
            prev = self._latest(fact_id, now)
            if prev is None or prev[6] is not None:
                raise TemporalError("Unknown or already ended fact")
            if valid_to <= prev[5]:
                raise TemporalError("valid_to must be after valid_from")
            self._write(fact_id, prev[0] + 1, prev[1], prev[2], prev[3], prev[4], prev[5], valid_to, evidence, "ended", now)

    # ---- reads -------------------------------------------------------------
    def as_of(self, domain, subject, predicate, valid_at, known_at=None):
        """Value believed at `known_at` (default now) to have held at `valid_at`; None if nothing was known."""
        if domain not in DOMAINS:
            raise TemporalError("Unknown domain")
        known = self.clock() if known_at is None else known_at
        ids = [r[0] for r in self.ledger.db.execute(
            "SELECT DISTINCT fact_id FROM fact_versions WHERE domain=? AND subject=? AND predicate=?",
            (domain, subject, predicate))]
        hits = []
        for fact_id in ids:
            row = self._latest(fact_id, known)
            if row and row[5] <= valid_at and (row[6] is None or valid_at < row[6]):
                hits.append((row[5], fact_id, strict_json(row[4]), json.loads(row[7])))
        if not hits:
            return None
        hits.sort()
        valid_from, fact_id, value, evidence = hits[-1]
        return {"fact_id": fact_id, "value": value, "valid_from": valid_from, "evidence": evidence}

    def history(self, fact_id):
        return [{"version": r[0], "value": strict_json(r[1]), "valid_from": r[2], "valid_to": r[3],
                 "recorded_at": r[4], "reason": r[5]} for r in self.ledger.db.execute(
                     "SELECT version,value,valid_from,valid_to,recorded_at,reason FROM fact_versions "
                     "WHERE fact_id=? ORDER BY version", (fact_id,))]
