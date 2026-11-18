"""Transactional local append-only decision/evolution journal.

    The process owner can replace this database. Hash chaining detects ordinary
    corruption; it is not a cryptographic defense against that owner rewriting
    the entire chain. Do not store personal dossiers here.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import sqlite3
import uuid

from .engine import canonical
from .schema import DOMAINS, identifier, strict_json


class Ledger:
    @classmethod
    def read_only(cls, workspace: Path):
        root = Path(workspace).resolve(strict=True)
        directory = root / 'runtime'
        path = directory / 'kernel.sqlite3'
        if directory.is_symlink() or path.is_symlink() or not path.is_file():
            raise ValueError('Existing regular local journal required')
        instance = cls.__new__(cls)
        instance.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=5, check_same_thread=False)
        try:
            instance.verify()
        except Exception:
            instance.close()
            raise
        return instance

    def __init__(self, workspace: Path):
        root = Path(workspace).resolve(strict=True)
        directory = root / "runtime"
        if directory.is_symlink():
            raise ValueError("Runtime symlinks forbidden")
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.stat().st_mode & 0o077:
            raise ValueError("Runtime directory must be private (mode 0700)")
        path = directory / "kernel.sqlite3"
        if path.is_symlink():
            raise ValueError("Database symlinks forbidden")
        fd = os.open(path, os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
        os.close(fd)
        if path.stat().st_mode & 0o077:
            raise ValueError("Database must be private (mode 0600)")
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5, check_same_thread=False)
        self.db.execute("PRAGMA busy_timeout=5000")
        # WAL: readers no longer wait for the one writer, and a writer no longer waits for readers
        # (three processes share this file: the API, the agent worker and timed scripts). The mode
        # is stored in the file, so every later connection, read-only ones included, uses it.
        # synchronous stays FULL: a ledger entry reported as written must survive a power cut.
        # The switch needs a moment with no other connection open; if another process holds the
        # file right now the PRAGMA just reports the old mode and the next start tries again.
        try:
            self.db.execute("PRAGMA journal_mode=WAL").fetchone()
        except sqlite3.OperationalError:
            pass
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
              kind TEXT NOT NULL, domain TEXT NOT NULL, payload TEXT NOT NULL,
              previous_hash TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
              BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
              BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        """)
        self.verify()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def transaction(self):
        # Nested workflows participate in their caller's atomic job transaction.
        nested = self.db.in_transaction
        savepoint = 'sp_' + uuid.uuid4().hex
        self.db.execute('SAVEPOINT ' + savepoint if nested else "BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute('RELEASE ' + savepoint if nested else "COMMIT")
        except BaseException:
            if nested:
                self.db.execute('ROLLBACK TO ' + savepoint)
                self.db.execute('RELEASE ' + savepoint)
            else:
                self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def digest(seq, key, kind, domain, payload, previous):
        return hashlib.sha256(canonical([seq, key, kind, domain, payload, previous]).encode()).hexdigest()

    def audit_chain(self) -> dict:
        """Phase 4a (brutal-honesty directive, 2026-11-15): the O(n) tamper-detection primitive.
        Walks the WHOLE chain from genesis and returns a structured result - it never raises for
        a tamper finding, so a caller can report the exact break point instead of catching an
        exception. {"ok": True, "length": N, "first_broken_seq": None, "reason": None} when
        intact, or {"ok": False, "length": <rows verified before the break>, "first_broken_seq":
        k, "reason": "..."} at the FIRST point the chain breaks. verify() below (used throughout
        this codebase to fail a write closed on a corrupted ledger) is unchanged and now
        implemented in terms of this walk, so the two can never disagree."""
        previous, seq = "0" * 64, 0
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            if row[0] != seq + 1:
                return {"ok": False, "length": seq, "first_broken_seq": row[0], "reason": "SEQUENCE_GAP_OR_OUT_OF_ORDER"}
            if row[5] != previous:
                return {"ok": False, "length": seq, "first_broken_seq": row[0], "reason": "PREVIOUS_HASH_MISMATCH"}
            if self.digest(*row[:6]) != row[6]:
                return {"ok": False, "length": seq, "first_broken_seq": row[0], "reason": "DIGEST_MISMATCH"}
            seq, previous = row[0], row[6]
        return {"ok": True, "length": seq, "first_broken_seq": None, "reason": None}

    def chain_head(self) -> dict | None:
        """O(1) read of the chain head - the 'chain head persisted' requirement. It is the last
        committed row's own (seq, digest): already durable in the events table itself, never a
        second denormalised value that could drift out of sync with it."""
        row = self.db.execute("SELECT seq, digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return None if row is None else {"seq": row[0], "digest": row[1]}

    def verify(self) -> int:
        result = self.audit_chain()
        if not result["ok"]:
            raise ValueError(f"Ledger integrity failure at seq {result['first_broken_seq']} ({result['reason']})")
        return result["length"]

    def _append(self, key, kind, domain, payload):
        identifier(key)
        if domain not in DOMAINS or kind not in {"decision", "evaluation", "promotion", "rejection", "rollback", "job"}:
            raise ValueError("Invalid event classification")
        encoded = canonical(payload)
        if len(encoded.encode()) > 1_048_576:
            raise ValueError("Journal event too large")
        self.verify()
        existing = self.db.execute("SELECT seq, kind, domain, payload FROM events WHERE event_key=?", (key,)).fetchone()
        if existing:
            if existing[1:] != (kind, domain, encoded):
                raise ValueError("Idempotency key conflicts with prior content")
            return existing[0]
        last = self.db.execute("SELECT seq, digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        seq, previous = (last[0] + 1, last[1]) if last else (1, "0" * 64)
        digest = self.digest(seq, key, kind, domain, encoded, previous)
        self.db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", (seq, key, kind, domain, encoded, previous, digest))
        return seq

    def append(self, key, kind, domain, payload):
        if kind not in {"decision", "evaluation", "rejection"}:
            raise ValueError("Version transitions require consider or rollback")
        with self.transaction():
            return self._append(key, kind, domain, payload)

    def records(self, domain):
        if domain not in DOMAINS:
            raise ValueError("Domain required")
        self.verify()
        return [{"seq": row[0], "key": row[1], "kind": row[2], "payload": strict_json(row[3])}
                for row in self.db.execute("SELECT seq,event_key,kind,payload FROM events WHERE domain=? ORDER BY seq", (domain,))]

    def champion(self, domain):
        champion = "baseline"
        for event in self.records(domain):
            if event["kind"] in {"promotion", "rollback"}:
                champion = event["payload"]["version"]
        return champion

    def consider(self, key, domain, receipt):
        """Only local fixture-checker versions; never an operational promotion."""
        from .lab import Receipt
        if not isinstance(receipt, Receipt):
            raise ValueError("Lab receipt required; input JSON cannot authorize promotion")
        receipt.validate()
        with self.transaction():
            old = self.champion(domain)
            prior = self.db.execute("SELECT payload FROM events WHERE event_key=?", (key,)).fetchone()
            if prior:
                old = strict_json(prior[0]).get("previous")
            against_champion = receipt.baseline == old and receipt.candidate != old
            kind = "promotion" if receipt.eligible and against_champion else "rejection"
            payload = {"version": receipt.candidate, "previous": old,
                       "scope": "LOCAL_SYNTHETIC_CHECKER_ONLY", "receipt": receipt.to_dict(),
                       "compared_to_current_champion": against_champion,
                       "operational_superiority_proven": False}
            return self._append(key, kind, domain, payload)

    def rollback(self, key, domain, target):
        identifier(target)
        with self.transaction():
            known = {"baseline"} | {x["payload"]["version"] for x in self.records(domain) if x["kind"] == "promotion"}
            if target not in known:
                raise ValueError("Unknown rollback version")
            return self._append(key, "rollback", domain, {"version": target, "scope": "LOCAL_SYNTHETIC_CHECKER_ONLY"})
