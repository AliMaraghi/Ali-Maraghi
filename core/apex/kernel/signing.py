"""Generic Ed25519 signing primitives (DPIF control 13 follow-up, 2026-11-15).

Wraps the EXACT SAME cryptography calls already proven in
core/apex/kernel/budget_signing.py (Phase 4's Budget SKU->price signing) - this is not a new
cryptographic design, it is the identical sign()/verify() call pattern, just not hardcoded to
price fields, so facts.py's assert_signed_fact()/verify_fact_signature() can reuse it for an
arbitrary field tuple. budget_signing.py is left untouched (already shipped, already tested);
nothing here replaces it.

Asymmetric, deliberately not HMAC, for the same reason as budget_signing.py: the verifier
only ever needs the PUBLIC key (no forgery power); the private key is supplied by the
caller at sign time and is never read from disk, written to disk, or logged by this module.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .engine import canonical


def sign_payload(private_key_bytes: bytes, *fields) -> bytes:
    sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return sk.sign(canonical(list(fields)).encode())


def verify_payload(public_key_bytes: bytes, signature: bytes, *fields) -> bool:
    """Returns False on any verification failure - never raises, never "unverifiable". A
    tampered field set, a wrong key, or a malformed signature all collapse to False."""
    pk = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    try:
        pk.verify(signature, canonical(list(fields)).encode())
        return True
    except (InvalidSignature, ValueError):
        return False
