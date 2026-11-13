"""Human approval for proposed actions: payload-bound, identity-bound, expiring, single use.

Every transition is appended to the existing hash-chained Ledger. Execution is
local and mock-only: it re-checks the operator Policy (kill state, zero budget,
domain) at execution time and never calls an external system.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from .engine import canonical
from .policy import Action, Policy, enforce_durable_stop
from .schema import DOMAINS, identifier, strict_json

PROPOSAL_TTL = 24 * 3600          # silence for 24 hours vetoes the proposal
APPROVAL_TTL = 15 * 60            # an issued approval link is short-lived
DAILY_ROUTINE_LIMIT = 3           # beyond this, proposals are deferred, never auto-approved
AGENT_PREFIX = "agent:"


class ApprovalError(PermissionError):
    pass


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


class ApprovalBook:
    def __init__(self, ledger, secret: bytes, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("Approval secret must be at least 32 bytes")
        self.ledger, self.secret, self.clock = ledger, secret, clock
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS proposals (
              id TEXT PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL,
              proposer TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
              created_at REAL NOT NULL, expires_at REAL NOT NULL, day TEXT NOT NULL,
              state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposal_commentary (
              id TEXT PRIMARY KEY, text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS approval_nonces (
              nonce TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, identity TEXT NOT NULL,
              payload_hash TEXT NOT NULL, expires_at REAL NOT NULL, used_at REAL);
        """)

    # ---- audit -------------------------------------------------------------
    def _audit(self, proposal_id, event, domain, detail, kind="decision"):
        key = identifier(f"appr.{proposal_id}.{event}"[:80])
        self.ledger._append(key, kind, domain, {"proposal": proposal_id, "event": event, **detail})

    def _row(self, proposal_id):
        row = self.ledger.db.execute(
            "SELECT id,domain,kind,proposer,payload,payload_hash,created_at,expires_at,state "
            "FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            raise ApprovalError("UNKNOWN_PROPOSAL")
        keys = ("id", "domain", "kind", "proposer", "payload", "payload_hash", "created_at", "expires_at", "state")
        return dict(zip(keys, row))

    # ---- lifecycle ---------------------------------------------------------
    def propose(self, proposal_id, domain, kind, proposer, payload, evidence_ids, commentary=None):
        identifier(proposal_id)
        if len(proposal_id) > 48:
            raise ValueError("Proposal id too long")
        identifier(kind)
        if domain not in DOMAINS:
            raise ValueError("Unknown domain")
        if not isinstance(proposer, str) or not proposer:
            raise ValueError("Proposer required")
        if not evidence_ids or not all(isinstance(e, str) and e for e in evidence_ids):
            raise ValueError("A proposal must cite evidence")
        body = {"payload": payload, "evidence": sorted(evidence_ids)}
        encoded = canonical(body)
        digest = payload_hash(body)
        now = self.clock()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self.ledger.transaction():
            # Every request admitted to the human queue today counts, whatever the later outcome,
            # so deny-and-repropose cannot be used to exceed the daily limit.
            admitted_today = self.ledger.db.execute(
                "SELECT COUNT(*) FROM proposals WHERE day=? AND state!='DEFERRED'", (day,)).fetchone()[0]
            state = "DEFERRED" if admitted_today >= DAILY_ROUTINE_LIMIT else "PENDING"
            self.ledger.db.execute(
                "INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?)",
                (proposal_id, domain, kind, proposer, encoded, digest, now, now + PROPOSAL_TTL, day, state))
            if commentary:
                # Model-generated text: stored apart from the payload, never hashed or approved.
                self.ledger.db.execute("INSERT INTO proposal_commentary VALUES (?,?)",
                                       (proposal_id, str(commentary)[:2000]))
            self._audit(proposal_id, "proposed", domain, {"state": state, "payload_hash": digest})
        return state

    def issue(self, proposal_id, identity):
        """Create a single-use approval token bound to payload hash, identity and expiry."""
        if not isinstance(identity, str) or not identity or identity.startswith(AGENT_PREFIX):
            raise ApprovalError("HUMAN_IDENTITY_REQUIRED")
        row = self._row(proposal_id)
        if row["state"] != "PENDING":
            raise ApprovalError("NOT_PENDING")
        if identity == row["proposer"]:
            raise ApprovalError("SELF_APPROVAL_DENIED")
        nonce = secrets.token_hex(16)
        expires = min(self.clock() + APPROVAL_TTL, row["expires_at"])
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT INTO approval_nonces VALUES (?,?,?,?,?,NULL)",
                                   (nonce, proposal_id, identity, row["payload_hash"], expires))
        return f"{nonce}.{self._sign(nonce, proposal_id, identity, row['payload_hash'], expires)}"

    def _sign(self, nonce, proposal_id, identity, digest, expires):
        message = canonical([nonce, proposal_id, identity, digest, round(expires, 3)]).encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def approve(self, proposal_id, token, identity):
        try:
            nonce, signature = token.split(".", 1)
        except (AttributeError, ValueError):
            raise ApprovalError("MALFORMED_TOKEN") from None
        with self.ledger.transaction():
            row = self._row(proposal_id)
            record = self.ledger.db.execute(
                "SELECT proposal_id,identity,payload_hash,expires_at,used_at FROM approval_nonces WHERE nonce=?",
                (nonce,)).fetchone()
            if record is None or record[0] != proposal_id:
                raise ApprovalError("UNKNOWN_TOKEN")
            _, bound_identity, bound_hash, expires, used = record
            expected = self._sign(nonce, proposal_id, bound_identity, bound_hash, expires)
            if not hmac.compare_digest(expected, signature):
                raise ApprovalError("BAD_SIGNATURE")
            if used is not None:
                raise ApprovalError("REPLAY")
            if identity != bound_identity:
                raise ApprovalError("IDENTITY_MISMATCH")
            now = self.clock()
            if now > expires:
                raise ApprovalError("TOKEN_EXPIRED")
            if row["state"] != "PENDING" or now > row["expires_at"]:
                raise ApprovalError("NOT_PENDING")
            current = payload_hash(strict_json(row["payload"]))
            if current != row["payload_hash"] or current != bound_hash:
                tampered = row["domain"]
            else:
                tampered = None
                self.ledger.db.execute("UPDATE approval_nonces SET used_at=? WHERE nonce=?", (now, nonce))
                self.ledger.db.execute("UPDATE proposals SET state='APPROVED' WHERE id=?", (proposal_id,))
                self._audit(proposal_id, "approved", row["domain"], {"identity": identity, "payload_hash": current})
        if tampered:
            # Recorded in its own committed transaction so the rejection is never rolled back.
            with self.ledger.transaction():
                self._audit(proposal_id, "tamper", tampered, {"identity": identity}, kind="rejection")
            raise ApprovalError("PAYLOAD_TAMPERED")
        return "APPROVED"

    def deny(self, proposal_id, identity):
        with self.ledger.transaction():
            row = self._row(proposal_id)
            if row["state"] not in {"PENDING", "DEFERRED"}:
                raise ApprovalError("NOT_PENDING")
            self.ledger.db.execute("UPDATE proposals SET state='DENIED' WHERE id=?", (proposal_id,))
            self._audit(proposal_id, "denied", row["domain"], {"identity": identity}, kind="rejection")
        return "DENIED"

    def expire_stale(self):
        """Silence vetoes: pending proposals past their deadline become EXPIRED."""
        now = self.clock()
        expired = []
        with self.ledger.transaction():
            for pid, domain in self.ledger.db.execute(
                    "SELECT id,domain FROM proposals WHERE state IN ('PENDING','DEFERRED') AND expires_at < ?",
                    (now,)).fetchall():
                self.ledger.db.execute("UPDATE proposals SET state='EXPIRED' WHERE id=?", (pid,))
                self._audit(pid, "expired", domain, {}, kind="rejection")
                expired.append(pid)
        return expired

    def execute(self, proposal_id, policy: Policy):
        """Mock execution only: record the decision locally after re-checking policy."""
        with self.ledger.transaction():
            row = self._row(proposal_id)
            if row["state"] != "APPROVED":
                raise ApprovalError("NOT_APPROVED")
            if payload_hash(strict_json(row["payload"])) != row["payload_hash"]:
                raise ApprovalError("PAYLOAD_TAMPERED")
            action = Action(idempotency_key=f"exec.{proposal_id}", kind="record_decision",
                            domain=row["domain"], estimated_pence=0, sensitivity="synthetic")
            allowed, reason = policy.authorize(action)
            if allowed:
                try:
                    enforce_durable_stop(self.ledger)
                except PermissionError:
                    allowed, reason = False, "DURABLE_STOP_ACTIVE"
            if allowed:
                self.ledger.db.execute("UPDATE proposals SET state='EXECUTED' WHERE id=?", (proposal_id,))
                self._audit(proposal_id, "executed", row["domain"],
                            {"mode": "MOCK_LOCAL_RECORD", "actions_executed": [], "reason": reason})
        if not allowed:
            with self.ledger.transaction():
                self._audit(proposal_id, "blocked." + reason.lower()[:20], row["domain"],
                            {"reason": reason}, kind="rejection")
            raise ApprovalError(reason)
        return "EXECUTED"

    def state(self, proposal_id):
        return self._row(proposal_id)["state"]

    def release_deferred(self):
        """Move deferred proposals into today's queue, oldest first, within the daily limit.

        Never approves anything; only makes a still-valid proposal reviewable.
        """
        now = self.clock()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        released = []
        with self.ledger.transaction():
            admitted = self.ledger.db.execute(
                "SELECT COUNT(*) FROM proposals WHERE day=? AND state!='DEFERRED'", (day,)).fetchone()[0]
            rows = self.ledger.db.execute(
                "SELECT id,domain FROM proposals WHERE state='DEFERRED' AND expires_at>=? ORDER BY created_at, id",
                (now,)).fetchall()
            for pid, domain in rows:
                if admitted >= DAILY_ROUTINE_LIMIT:
                    break
                self.ledger.db.execute("UPDATE proposals SET state='PENDING', day=? WHERE id=?", (day, pid))
                self._audit(pid, "released", domain, {})
                admitted += 1
                released.append(pid)
        return released

    def view(self, proposal_id):
        """Trusted, application-generated facts for display; commentary is kept separate."""
        row = self._row(proposal_id)
        body = strict_json(row["payload"])
        commentary = self.ledger.db.execute(
            "SELECT text FROM proposal_commentary WHERE id=?", (proposal_id,)).fetchone()
        return {"id": row["id"], "domain": row["domain"], "kind": row["kind"], "proposer": row["proposer"],
                "state": row["state"], "payload": body["payload"], "evidence": body["evidence"],
                "payload_hash": row["payload_hash"], "created_at": row["created_at"],
                "decision_deadline": row["expires_at"], "approval_token_ttl_seconds": APPROVAL_TTL,
                "model_commentary": commentary[0] if commentary else None}

    def listing(self):
        return [{"id": r[0], "kind": r[1], "state": r[2], "decision_deadline": r[3]}
                for r in self.ledger.db.execute(
                    "SELECT id,kind,state,expires_at FROM proposals ORDER BY created_at DESC, id LIMIT 50")]
