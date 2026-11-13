"""Encrypted personal dossier with an append-only access log. Status: TESTS_NOT_RUN.

Per the manifesto: dossier records are encrypted with AES-256 (AES-256-GCM here, authenticated, unique 96-bit nonce per record, AAD binds tier+key+key version so a
ciphertext cannot be moved to another key or tier), the key lives in a separate private file (never the n8n key, never in the database), and EVERY access attempt - allowed or
denied - is written to an append-only log without any plaintext. Level-4 data never goes to an agent or model: it can only be read by the LocalCli requester (the owner's local
command-line tool). Agents are bounded by their registry tier ceiling (and key prefixes for 8-8). When APEX_DATA_SOURCE=corporate every agent read is refused.
LIMITS: this is VPS-side storage in the local SQLite journal; the specification keeps level-4 data (exact location, medical, account numbers) off the VPS entirely, so do NOT store tier-4
values here until the owner decides where raw data may live (the module permits it only for LocalCli and flags it in the log).
"""
from __future__ import annotations

import base64
import json
import os
import re
import stat
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .. import agents_registry
from .schema import identifier

KEY_VERSION_RE = re.compile(r"[A-Za-z0-9._-]{1,32}")
MAX_VALUE_BYTES = 16_384


class DossierError(PermissionError):
    pass


@dataclass(frozen=True)
class Requester:
    kind: str          # "agent" or "local_cli"
    ident: str         # agent id, or an operator label

    @staticmethod
    def agent(agent_id):
        return Requester("agent", agent_id)

    @staticmethod
    def local_cli(label="owner-cli"):
        return Requester("local_cli", label)


def load_key(path):
    """Read a 32-byte AES key (base64url) from a private 0600 file owned by the current user or root. Never logged."""
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid not in (os.getuid(), 0) or info.st_size > 256:
        raise ValueError("Key file must be a private regular file")
    with open(path, "rb") as stream:
        text = stream.read().strip()
    raw = base64.urlsafe_b64decode(text + b"=" * (-len(text) % 4))
    if len(raw) != 32:
        raise ValueError("AES-256 key must be exactly 32 bytes")
    return raw


class Dossier:
    def __init__(self, ledger, key: bytes, key_version="k1", clock=time.time, data_source=None):
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise ValueError("AES-256 key must be exactly 32 bytes")
        if not KEY_VERSION_RE.fullmatch(key_version):
            raise ValueError("Invalid key version")
        self.ledger, self.clock, self.key_version = ledger, clock, key_version
        self._aes = AESGCM(bytes(key))
        self.data_source = data_source if data_source is not None else os.environ.get("APEX_DATA_SOURCE", "personal")
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS personal_dossier (
              key TEXT NOT NULL, tier INTEGER NOT NULL CHECK(tier BETWEEN 1 AND 4), key_version TEXT NOT NULL,
              nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, written_at REAL NOT NULL, PRIMARY KEY(key, key_version));
            CREATE TABLE IF NOT EXISTS dossier_access_log (
              seq INTEGER PRIMARY KEY, at REAL NOT NULL, requester_kind TEXT NOT NULL, requester TEXT NOT NULL,
              operation TEXT NOT NULL, key TEXT NOT NULL, tier INTEGER, outcome TEXT NOT NULL, reason TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS dossier_log_no_update BEFORE UPDATE ON dossier_access_log BEGIN SELECT RAISE(ABORT,'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS dossier_log_no_delete BEFORE DELETE ON dossier_access_log BEGIN SELECT RAISE(ABORT,'append-only'); END;
        """)

    def _log(self, who, operation, key, tier, outcome, reason):
        with self.ledger.transaction():
            self.ledger.db.execute(
                "INSERT INTO dossier_access_log (at,requester_kind,requester,operation,key,tier,outcome,reason) VALUES (?,?,?,?,?,?,?,?)",
                (self.clock(), who.kind, who.ident[:64], operation, key[:128], tier, outcome, reason))

    @staticmethod
    def _aad(key, tier, version):
        return f"{key}|{tier}|{version}".encode()

    def _authorise(self, who, key, tier):
        """Return a reason string if DENIED, else None."""
        if who.kind == "local_cli":
            return None
        if who.kind != "agent":
            return "UNKNOWN_REQUESTER"
        if self.data_source == "corporate":
            return "CORPORATE_SOURCE_DENIED"
        if tier == 4:
            return "TIER4_LOCAL_CLI_ONLY"
        try:
            spec = agents_registry.get(who.ident)
        except (KeyError, PermissionError):
            return "AGENT_UNKNOWN_OR_UNRESOLVED"
        if tier > spec.max_dossier_tier:
            return "TIER_ABOVE_AGENT_CEILING"
        if spec.key_prefixes and not key.startswith(spec.key_prefixes):
            return "KEY_PREFIX_NOT_ALLOWED"
        return None

    def put(self, who, key, tier, value):
        if not isinstance(key, str) or len(key) > 80:
            raise ValueError("Invalid dossier key")
        identifier(key)                                  # conservative key shape; dots allowed for prefixes like lang.
        if who.kind != "local_cli":
            self._log(who, "put", key, tier, "DENIED", "WRITE_LOCAL_CLI_ONLY")
            raise DossierError("WRITE_LOCAL_CLI_ONLY")
        if type(tier) is not int or not 1 <= tier <= 4:
            raise ValueError("tier must be 1..4")
        plain = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        if len(plain) > MAX_VALUE_BYTES:
            raise ValueError("Value too large")
        nonce = os.urandom(12)
        blob = self._aes.encrypt(nonce, plain, self._aad(key, tier, self.key_version))
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT OR REPLACE INTO personal_dossier VALUES (?,?,?,?,?,?)",
                                   (key, tier, self.key_version, nonce, blob, self.clock()))
        self._log(who, "put", key, tier, "OK", "TIER4_STORED_ON_VPS" if tier == 4 else "STORED")

    def get(self, who, key):
        row = self.ledger.db.execute(
            "SELECT tier,key_version,nonce,ciphertext FROM personal_dossier WHERE key=? AND key_version=?",
            (key, self.key_version)).fetchone()
        if row is None:
            self._log(who, "get", key, None, "DENIED", "NOT_FOUND")
            raise DossierError("NOT_FOUND")
        tier, version, nonce, blob = row
        reason = self._authorise(who, key, tier)
        if reason:
            self._log(who, "get", key, tier, "DENIED", reason)
            raise DossierError(reason)
        try:
            plain = self._aes.decrypt(nonce, blob, self._aad(key, tier, version))
        except Exception:
            self._log(who, "get", key, tier, "DENIED", "DECRYPTION_FAILED")
            raise DossierError("DECRYPTION_FAILED") from None
        self._log(who, "get", key, tier, "OK", "READ")
        return json.loads(plain)

    def access_log(self, limit=100):
        return [dict(zip(("seq", "at", "requester_kind", "requester", "operation", "key", "tier", "outcome", "reason"), r))
                for r in self.ledger.db.execute("SELECT * FROM dossier_access_log ORDER BY seq DESC LIMIT ?", (min(limit, 1000),))]
