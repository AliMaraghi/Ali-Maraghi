"""Mutual-match platform core (brutal-honesty directive, 2026-11-15, Mission 2).

A SEPARATE prototype from APEX's own kernel - this is a different product (a dating
platform), not a personal-assistant component, so it is not built on APEX's append-only
Ledger (that store is explicitly for provenance of AI-agent decisions, not for a real
consumer product's own user data model, and its append-only design is wrong for a user's
own right-to-delete). This module uses its own plain SQLite schema with real UPDATE/DELETE
where the product genuinely needs them (account deletion).

Design, following the mission's own rules:
  - No message is ever sent without a confirmed MUTUAL match (both users liked each other).
  - Sensitive data (gender, orientation, marital status) is stored in a SEPARATE, Fernet-
    encrypted table from public profile fields, never mixed in the same row/query.
  - A rate limit caps likes per user per day (anti-spam, configurable per deployment).
  - Full account deletion is REAL deletion (unlike APEX's facts store) - this product's
    users have a real right to erasure, and this schema is new enough to honour it.
  - report() always creates a block immediately AND a pending-review record - "report and
    block fast, resolve the review within 24h" per the mission's own S3 gate; the BLOCK
    itself is immediate (not waiting on review), the review SLA is the <24h part.

HONEST SCOPE: this is prototype domain logic for a 10,000+-user design, proven with
synthetic fixtures (real SQLite, real encryption, real rate-limit enforcement) - it is NOT
a deployed service. Real infrastructure (hosting, a photo-verification vendor for selfie
matching, app-store review, legal review of the actual Terms) is explicitly out of scope
and not built here.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from cryptography.fernet import Fernet

DEFAULT_DAILY_LIKE_LIMIT = 100
REPORT_REVIEW_SLA_SECONDS = 24 * 3600


class PlatformError(PermissionError):
    pass


@dataclass(frozen=True)
class Profile:
    user_id: str
    display_name: str
    age: int
    search_min_age: int
    search_max_age: int


class MutualMatchPlatform:
    def __init__(self, db_path: str, encryption_key: bytes | None = None, now=time.time,
                 daily_like_limit: int = DEFAULT_DAILY_LIKE_LIMIT):
        """`encryption_key` is a Fernet key for the SEPARATE sensitive-data table. If not
        supplied, one is generated for this instance only - exactly like every ephemeral
        signing key elsewhere in this codebase, never written to disk by this class itself.
        A real deployment's key-custody decision is the same open question as
        docs/key_custody_decision.md already names for APEX's own signing keys."""
        self.db = sqlite3.connect(db_path)
        self.now = now
        self.daily_like_limit = daily_like_limit
        self._fernet = Fernet(encryption_key or Fernet.generate_key())
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
              user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, age INTEGER NOT NULL,
              search_min_age INTEGER NOT NULL, search_max_age INTEGER NOT NULL,
              photo_verified INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sensitive_profile_data (
              user_id TEXT PRIMARY KEY, encrypted_blob BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS likes (
              liker_id TEXT NOT NULL, liked_id TEXT NOT NULL, created_at REAL NOT NULL,
              PRIMARY KEY (liker_id, liked_id));
            CREATE TABLE IF NOT EXISTS blocks (
              blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL, created_at REAL NOT NULL,
              PRIMARY KEY (blocker_id, blocked_id));
            CREATE TABLE IF NOT EXISTS reports (
              id INTEGER PRIMARY KEY, reporter_id TEXT NOT NULL, reported_id TEXT NOT NULL,
              reason TEXT NOT NULL, created_at REAL NOT NULL, resolved_at REAL,
              resolution TEXT);
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY, sender_id TEXT NOT NULL, recipient_id TEXT NOT NULL,
              body TEXT NOT NULL, created_at REAL NOT NULL);
        """)

    # ---- profile -------------------------------------------------------
    def create_profile(self, user_id: str, display_name: str, age: int,
                       search_min_age: int, search_max_age: int,
                       sensitive: dict) -> None:
        """`sensitive` (gender, orientation, marital_status, ...) is encrypted and stored in
        a SEPARATE table, keyed by user_id only - never joined against public profile
        fields in the same query, so a leak of the public table alone reveals nothing
        sensitive."""
        if age < 18:
            raise PlatformError("AGE_VERIFICATION_FAILED: under 18")
        if search_min_age < 18:
            raise PlatformError("AGE_VERIFICATION_FAILED: search range below 18")
        now = self.now()
        self.db.execute(
            "INSERT INTO profiles VALUES (?,?,?,?,?,0,?)",
            (user_id, display_name, age, search_min_age, search_max_age, now))
        import json
        encrypted = self._fernet.encrypt(json.dumps(sensitive).encode())
        self.db.execute("INSERT INTO sensitive_profile_data VALUES (?,?)", (user_id, encrypted))
        self.db.commit()

    def verify_photo(self, user_id: str) -> None:
        """Marks photo_verified=True. The REAL selfie<->photo-match check is a separate,
        owner-gated decision (which vendor, what threshold) - this method is the schema
        hook a real verification result would call, not a verification implementation."""
        self.db.execute("UPDATE profiles SET photo_verified=1 WHERE user_id=?", (user_id,))
        self.db.commit()

    def delete_account(self, user_id: str) -> dict:
        """REAL deletion - unlike APEX's own append-only facts store, this schema is new
        enough to support a genuine right-to-erasure. Removes the profile, sensitive data,
        every like/block/message/report row touching this user, in one transaction."""
        counts = {}
        with self.db:
            for table, cols in (
                ("profiles", ["user_id"]),
                ("sensitive_profile_data", ["user_id"]),
                ("likes", ["liker_id", "liked_id"]),
                ("blocks", ["blocker_id", "blocked_id"]),
                ("messages", ["sender_id", "recipient_id"]),
                ("reports", ["reporter_id", "reported_id"]),
            ):
                for col in cols:
                    cur = self.db.execute(f"DELETE FROM {table} WHERE {col}=?", (user_id,))
                    counts[f"{table}.{col}"] = cur.rowcount
        return counts

    # ---- likes / matching -----------------------------------------------
    def _likes_today(self, user_id: str) -> int:
        day_start = self.now() - (self.now() % 86400)
        return self.db.execute(
            "SELECT COUNT(*) FROM likes WHERE liker_id=? AND created_at>=?",
            (user_id, day_start)).fetchone()[0]

    def like(self, liker_id: str, liked_id: str) -> bool:
        """Returns True if this like completes a MUTUAL match (the other user already
        liked this one), False otherwise. Rate-limited to daily_like_limit per user - anti-
        spam, not a monetization lever (the mission's own rule: no "pay to be seen" trap)."""
        if liker_id == liked_id:
            raise PlatformError("CANNOT_LIKE_SELF")
        if self._is_blocked(liker_id, liked_id) or self._is_blocked(liked_id, liker_id):
            raise PlatformError("BLOCKED_PAIR")
        if self._likes_today(liker_id) >= self.daily_like_limit:
            raise PlatformError(f"DAILY_LIKE_LIMIT_EXCEEDED:{self.daily_like_limit}")
        self.db.execute("INSERT OR IGNORE INTO likes VALUES (?,?,?)", (liker_id, liked_id, self.now()))
        self.db.commit()
        return self.is_mutual_match(liker_id, liked_id)

    def is_mutual_match(self, user_a: str, user_b: str) -> bool:
        a_liked_b = self.db.execute("SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?",
                                    (user_a, user_b)).fetchone() is not None
        b_liked_a = self.db.execute("SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?",
                                    (user_b, user_a)).fetchone() is not None
        return a_liked_b and b_liked_a

    def visible_profiles_for(self, user_id: str) -> list:
        """'User A only sees profiles that B has ALSO liked A' - the mission's own S2 rule,
        read literally: this returns who's visible to A in the sense of "already in a
        mutual match", not the discovery/browse feed (which would show everyone in range,
        pre-match - a separate, unimplemented feature). Blocked pairs excluded either
        direction."""
        rows = self.db.execute(
            "SELECT l2.liker_id FROM likes l1 JOIN likes l2 "
            "ON l1.liker_id = l2.liked_id AND l1.liked_id = l2.liker_id "
            "WHERE l1.liker_id=?", (user_id,)).fetchall()
        return [r[0] for r in rows if not self._is_blocked(user_id, r[0]) and not self._is_blocked(r[0], user_id)]

    # ---- messaging --------------------------------------------------------
    def send_message(self, sender_id: str, recipient_id: str, body: str) -> int:
        """The mission's own hard rule, enforced structurally: no message without a
        confirmed mutual match. Raises, never silently drops."""
        if self._is_blocked(sender_id, recipient_id) or self._is_blocked(recipient_id, sender_id):
            raise PlatformError("BLOCKED_PAIR")
        if not self.is_mutual_match(sender_id, recipient_id):
            raise PlatformError("NO_MUTUAL_MATCH")
        if not body or not body.strip():
            raise PlatformError("EMPTY_MESSAGE")
        cur = self.db.execute("INSERT INTO messages (sender_id, recipient_id, body, created_at) VALUES (?,?,?,?)",
                              (sender_id, recipient_id, body, self.now()))
        self.db.commit()
        return cur.lastrowid

    # ---- safety: block / report -------------------------------------------
    def _is_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?",
                               (blocker_id, blocked_id)).fetchone() is not None

    def block(self, blocker_id: str, blocked_id: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO blocks VALUES (?,?,?)", (blocker_id, blocked_id, self.now()))
        self.db.commit()

    def report(self, reporter_id: str, reported_id: str, reason: str) -> int:
        """Reporting ALWAYS blocks immediately (the mission's rule: 'report and block fast')
        and creates a pending review row with a 24h SLA - review_overdue() below is the
        thing an operator's dashboard would poll."""
        self.block(reporter_id, reported_id)
        cur = self.db.execute(
            "INSERT INTO reports (reporter_id, reported_id, reason, created_at, resolved_at, resolution) "
            "VALUES (?,?,?,?,NULL,NULL)", (reporter_id, reported_id, reason, self.now()))
        self.db.commit()
        return cur.lastrowid

    def resolve_report(self, report_id: int, resolution: str) -> None:
        self.db.execute("UPDATE reports SET resolved_at=?, resolution=? WHERE id=?",
                        (self.now(), resolution, report_id))
        self.db.commit()

    def review_overdue(self) -> list:
        """Reports still unresolved past the 24h SLA - what an operator must act on NOW."""
        cutoff = self.now() - REPORT_REVIEW_SLA_SECONDS
        rows = self.db.execute(
            "SELECT id, reporter_id, reported_id, reason, created_at FROM reports "
            "WHERE resolved_at IS NULL AND created_at < ?", (cutoff,)).fetchall()
        return [{"id": r[0], "reporter_id": r[1], "reported_id": r[2], "reason": r[3], "created_at": r[4]}
                for r in rows]
