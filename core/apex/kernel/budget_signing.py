"""Ed25519 signing for Budget SKU->price rows (Phase 4b, brutal-honesty directive 2026-11-15).

Asymmetric, deliberately not HMAC: the running agent process only ever needs to VERIFY a price
before spending against it, so it can hold the PUBLIC key - which grants no forgery power at
all - while the PRIVATE signing key is held only by whoever runs Budget.set_price() as the
pricing operator. Budget.price() (the read path every reservation goes through) never
requires, and never touches, the private key.

HONEST SCOPE: this module provides the primitive and Budget wires it in as an OPT-IN mode
(Budget(ledger, pricing_public_key=...)). The default, used by every existing caller in this
codebase today, remains unsigned - exactly as before this module existed - because turning
signing on for a real deployment means the owner generating a real keypair and deciding where
the private key lives, which is a production-secrets decision this change does not make for
them. See core/apex/kernel/budget.py's own docstring for exactly what changes when a public
key is supplied.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from .engine import canonical


def generate_keypair() -> tuple[bytes, bytes]:
    """Returns (private_key_bytes, public_key_bytes), each 32 raw bytes. For tests/fixtures and
    for an operator's own real key generation - this module makes no decision about where
    either half is stored."""
    sk = Ed25519PrivateKey.generate()
    return (sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()),
            sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def public_key_for(private_key_bytes: bytes) -> bytes:
    sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _payload(provider, sku, price_millipence, effective_from, currency, source, verified_at) -> bytes:
    return canonical([provider, sku, price_millipence, float(effective_from), currency, source,
                       float(verified_at)]).encode()


def sign_price(private_key_bytes: bytes, provider, sku, price_millipence, effective_from,
               currency, source, verified_at) -> bytes:
    sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return sk.sign(_payload(provider, sku, price_millipence, effective_from, currency, source, verified_at))


def verify_price(public_key_bytes: bytes, signature: bytes, provider, sku, price_millipence,
                  effective_from, currency, source, verified_at) -> bool:
    pk = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    try:
        pk.verify(signature, _payload(provider, sku, price_millipence, effective_from, currency, source, verified_at))
        return True
    except InvalidSignature:
        return False
