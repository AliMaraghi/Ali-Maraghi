"""Approval-tiering POLICY layer (brutal-honesty directive, 2026-11-15, section 4.1).

HONEST SCOPE, stated up front: this module classifies action kinds into
"always_allow" (low blast-radius, informational, no money/communication/
system-change effect) or "always_ask" (everything else, by default). It does
NOT and architecturally CANNOT skip core/apex/kernel/approvals.py's human
gate: ApprovalBook.approve() requires a signed, single-use token from
ApprovalBook.issue(), and issue() itself refuses an agent identity (anything
starting with AGENT_PREFIX) and refuses self-approval. Nothing in this module,
or anywhere it calls, ever calls issue() or approve(). A classification of
"always_allow" here only (a) marks whether a kind is even ELIGIBLE for a
future, separately-authorized local approver to act on - that approver is not
built and is explicitly out of scope of this change - and (b) is journaled
with its reason so an owner auditing the Ledger can see exactly why. Every
proposal of every tier still sits PENDING, exactly as before this module
existed, until a real human runs through issue()/approve() by hand or via
/console. This is the only way to add tiering without building a way to
fabricate an owner's decision, which this project does not do, under any
framing, ever.

The money/communication/system-change set below is PINNED as a literal
frozenset in code - not data, not a config file, not overridable at runtime -
because the one invariant this module exists to protect is that nothing here
can ever move that set to always_allow. It may only grow (more caution),
never shrink.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import identifier

ALWAYS_ALLOW = "always_allow"
ALWAYS_ASK = "always_ask"

_PINNED_ALWAYS_ASK_KINDS = frozenset({
    "finance_action_proposal",     # A-8: an ESPP exercise/hold decision - money
    "capability_proposal",         # grows the system's own capability registry
    "telegram_notify", "gmail_draft", "outlook_draft", "laptop_browser_task",  # external comms/action adapters
    "mock_notify",                  # adapter-backed; pinned out of caution even though harmless
})

# The ONLY kinds eligible for always_allow - an explicit allowlist, never a
# default. A kind not listed here - including any kind added to the Gateway
# after this module was written - defaults to always_ask.
_AUTO_ELIGIBLE_KINDS = frozenset({
    "record_decision",             # a local text note; no effect beyond the Ledger's own record
    "research_brief_proposal",     # informational draft, adapter=None, no money/comms
})


@dataclass(frozen=True)
class TierDecision:
    kind: str
    tier: str
    reason: str


def tier_for(kind: str, kind_spec=None) -> TierDecision:
    """Pure, deterministic classification - a function of the KIND's own definition
    only, never of a specific proposal's payload content."""
    if kind in _PINNED_ALWAYS_ASK_KINDS:
        return TierDecision(kind, ALWAYS_ASK,
                             f"PINNED: '{kind}' is in the permanent money/communication/system-change set")
    if kind_spec is not None and getattr(kind_spec, "adapter", None) is not None:
        return TierDecision(kind, ALWAYS_ASK,
                             f"'{kind}' has adapter={kind_spec.adapter!r} - any adapter-backed kind is always_ask by default")
    if kind in _AUTO_ELIGIBLE_KINDS:
        return TierDecision(kind, ALWAYS_ALLOW,
                             f"'{kind}' is on the explicit low-blast-radius allowlist (informational, adapter=None)")
    return TierDecision(kind, ALWAYS_ASK, f"'{kind}' is not on the always_allow allowlist - default-deny")


def journal_decision(ledger, proposal_id: str, domain: str, decision: TierDecision) -> int:
    """Records the tiering decision and its reason in the existing hash-chained Ledger -
    an audit trail only, never an approval action. Idempotent: re-journaling the same
    proposal with the same decision is a no-op (Ledger._append's own idempotency key)."""
    key = identifier(f"tier.{proposal_id}"[:80])
    return ledger._append(key, "decision", domain,
                           {"proposal": proposal_id, "event": "tiering_decision",
                            "kind": decision.kind, "tier": decision.tier, "reason": decision.reason})
