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
        instance.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=5)
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
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.execute("PRAGMA busy_timeout=5000")
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

    def verify(self) -> int:
        previous = "0" * 64
        seq = 0
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            if row[0] != seq + 1 or row[5] != previous or self.digest(*row[:6]) != row[6]:
                raise ValueError("Ledger integrity failure")
            seq, previous = row[0], row[6]
        return seq

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
