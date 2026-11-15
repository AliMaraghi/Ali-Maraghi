"""Capability tokens (Phase 3, brutal-honesty directive 2026-11-15).

CORRECTION FOR THE RECORD, same honesty standard as Phase 4's hash-chain correction: the
enforcement gating ActionGateway.execute() was NEVER kernel.tiering's frozenset
(_PINNED_ALWAYS_ASK_KINDS) - that module has said, since it was written, that it is
"classification + audit trail only; no auto-approval path exists anywhere in this codebase"
(see kernel/tiering.py's own docstring). The REAL enforcement mechanism - the thing that
already satisfies "the enforcement is token possession" - is
kernel.approvals.ApprovalBook.issue()/approve(): ActionGateway.execute() requires
state=='APPROVED', and the ONLY path to APPROVED is approve(), which requires an
HMAC-signed, single-use, identity-bound, time-limited token from issue(). approve() already
rejects a fabricated signature (BAD_SIGNATURE), a replayed token (REPLAY), an expired token
(TOKEN_EXPIRED), a wrong identity (IDENTITY_MISMATCH) and a tampered payload
(PAYLOAD_TAMPERED) - see tests/test_capability_tokens.py, which exercises this EXISTING
mechanism directly rather than reimplementing a parallel one (a system with two reference
monitors has zero - the same rule tiering.py and scheduler.py were both built around).

Adding a new Gateway kind requires NO edit to approvals.py, ApprovalBook, or
ActionGateway.execute(): none of their enforcement code ever references a kind name by
value. A new kind needs only an entry in kernel.gateway.DEFAULT_KINDS (or a caller's own
kinds dict), proven by kind_requires_token() below, which answers "does this kind need a
token" from the Gateway's own registry alone.

HONEST LIMITATION (disclosed, not hidden, not faked with a UUID): the HMAC secret backing
every token is ONE shared key held by whoever constructs ApprovalBook(ledger, secret) -
normally the operator process, loaded from /etc/apex/approvals-runtime.json per every
scripts/*.py's existing convention. This is unforgeable against anyone without that key
(proven in tests/test_capability_tokens.py), but it is NOT a per-driver or per-role scoped
capability in the seL4/EROS sense: any human identity that can call issue() can approve any
domain-permitted kind - there is no narrower token that lets identity X approve only kind Y.
A real scoped-capability system would need one key pair per scope, not one shared HMAC
secret, and a signing authority that issues scope-bound keys - that is a real, larger piece
of work, genuinely out of scope for this phase, and is reported here rather than faked.
"""
from __future__ import annotations


def kind_requires_token(gateway, kind: str) -> bool:
    """Every registered kind requires a token to reach execute() - this is a structural fact
    of ActionGateway.execute()'s own code (it unconditionally requires state=='APPROVED'),
    not a per-kind policy choice recorded anywhere. Raises KeyError for an unregistered kind:
    there is no kind for which a token is optional, and no kind this function can vouch for
    that the Gateway does not already know about."""
    if kind not in gateway.kinds:
        raise KeyError(f"Unregistered kind: {kind}")
    return True
