"""HMAC request/response signing for the laptop bridge (stdlib). Status: see tests/test_bridge.py.

The laptop agent and the VPS share ONE random 256-bit key that is created in the Access-protected console and shown once. Every request carries
X-Apex-Key-Id, X-Apex-Ts, X-Apex-Nonce and X-Apex-Sig = HMAC-SHA256(key, METHOD\\nPATH\\nTS\\nNONCE\\nSHA256(body)); the server rejects stale timestamps (+-60 s) and repeated nonces. Responses carry
X-Apex-Resp-Sig = HMAC-SHA256(key, NONCE\\nSTATUS\\nSHA256(body)), so the laptop only acts on answers produced by whoever holds the key. The key never travels on the wire and is never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import time
from pathlib import Path

WINDOW_SECONDS = 60
MAX_NONCES = 10_000


class AuthError(PermissionError):
    pass


def key_file(root):
    return Path(root) / "runtime" / "secrets" / "bridge_key.json"


def create_key(root, now=None):
    """Create (or rotate) the shared key. Returns the one-time display string 'KEYID.KEYHEX'; only this call ever returns the secret."""
    path = key_file(root)
    (Path(root) / "runtime").mkdir(mode=0o700, exist_ok=True)        # the journal requires a private runtime folder; never create it world-readable
    path.parent.mkdir(mode=0o700, exist_ok=True)
    key_id, key = secrets.token_hex(4), secrets.token_hex(32)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"key_id": key_id, "key": key, "created": int(now if now is not None else time.time())}, stream)
    os.replace(tmp, path)
    return f"{key_id}.{key}"


def load_key(root):
    """Return (key_id, key_bytes) or None when no key exists. Refuses a key file that others can read."""
    path = key_file(root)
    if not path.exists():
        return None
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise AuthError("Bridge key file must be a private regular file")
    data = json.loads(path.read_text())
    return data["key_id"], bytes.fromhex(data["key"])


def _body_hash(body):
    return hashlib.sha256(body).hexdigest()


def sign_request(key, method, path, ts, nonce, body):
    message = f"{method}\n{path}\n{ts}\n{nonce}\n{_body_hash(body)}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def sign_response(key, nonce, status, body):
    return hmac.new(key, f"{nonce}\n{status}\n{_body_hash(body)}".encode(), hashlib.sha256).hexdigest()


class NonceCache:
    def __init__(self, clock=time.time):
        self.clock, self.seen = clock, {}

    def check_and_add(self, nonce):
        now = self.clock()
        if len(self.seen) >= MAX_NONCES:
            self.seen = {n: t for n, t in self.seen.items() if t > now}
        if nonce in self.seen and self.seen[nonce] > now:
            return False
        self.seen[nonce] = now + 2 * WINDOW_SECONDS
        return True


def verify_request(key_id, key, headers, method, path, body, nonces, now=None):
    """Raise AuthError (never revealing why in detail to the client) unless the request is authentic, fresh and not replayed."""
    now = time.time() if now is None else now
    try:
        got_id, ts, nonce, sig = headers["x-apex-key-id"], headers["x-apex-ts"], headers["x-apex-nonce"], headers["x-apex-sig"]
        ts_int = int(ts)
    except (KeyError, ValueError):
        raise AuthError("missing or malformed auth headers") from None
    if not (len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce)):
        raise AuthError("bad nonce")
    expected = sign_request(key, method, path, ts, nonce, body)
    if not (hmac.compare_digest(got_id, key_id) and hmac.compare_digest(sig, expected)):
        raise AuthError("bad signature")
    if abs(now - ts_int) > WINDOW_SECONDS:
        raise AuthError("stale timestamp")
    if not nonces.check_and_add(nonce):
        raise AuthError("replay")
    return nonce
