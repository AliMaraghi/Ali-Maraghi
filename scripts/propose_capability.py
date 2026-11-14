#!/usr/bin/env python3
"""Propose a NEW capability for a request none of the 7 registered ones cover - the drafting
step done by an LLM instead of the owner, nothing more. This is deliberately bounded by the same
"controlled evolution" doctrine as the rest of this project (AGENTS.md): it proposes, it never
tests, deploys, or adopts. The draft is inert text sitting in a PENDING row in the existing
ApprovalBook; nothing imports it, execs it, writes it to a .py file, or wires it into
scripts/orchestrator.py's _CAPABILITY_REGISTRY. Test-writing, sandboxed evaluation and wiring the
capability in for real all remain separate, deliberate owner actions - exactly the same gap that
already exists between a research_brief_proposal (A-2) and an actually-published brief.

What this DOES do, for real:
  1. Records the unmet request as a fact (core/apex/kernel/facts.py, subject "owner",
     predicate "capability_gap") - so repeated requests for the same missing thing are visible
     in the fact history even before anyone acts on them.
  2. Makes exactly ONE budget-gated LLM call (SKU "capability-draft-step") asking for a short
     draft: a proposed capability name/description plus a candidate Python function in the same
     style as core/apex/agents_impl.py's pure functions.
  3. Submits that draft through the existing ActionGateway/ApprovalBook as kind
     "capability_proposal" (adapter=None - local record only, same pattern as A-2's
     research_brief_proposal) - visible on /console like any other pending proposal, and subject
     to the same daily PENDING/DEFERRED cap.

Usage:
  python3 scripts/propose_capability.py --text "whatever the user asked for that had no matching capability"
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import facts as factstore                           # noqa: E402
from apex.kernel.budget import Budget, BudgetDenied                  # noqa: E402
from apex.kernel.approvals import ApprovalBook                       # noqa: E402
from apex.kernel.gateway import ActionGateway, KindSpec               # noqa: E402
from apex.kernel.memory import Ledger                                 # noqa: E402
from apex.kernel.schema import identifier                             # noqa: E402

PROVIDER, SKU = "anthropic", "capability-draft-step"

CAPABILITY_PROPOSAL_KIND = KindSpec(
    frozenset({"opportunity"}),
    {"capability_name": str, "trigger_text": str, "draft_code": str, "draft_notes": str})


def draft_capability(budget, text: str) -> dict:
    """The ONE LLM call. Raises BudgetDenied/ResearchPipelineError on failure - the caller decides
    what to do; this function never silently fabricates a draft."""
    from apex.agents_research import call_anthropic, load_api_key
    key = f"capability.draft.{int(time.time() * 1000)}"
    budget.reserve(key, "core", PROVIDER, SKU, 1)
    try:
        api_key = load_api_key()
        raw = call_anthropic(
            api_key,
            "A user asked for something no existing capability covers. Propose ONE new capability "
            "to add. Reply in exactly this format, nothing else:\n"
            "NAME: <short_capability_name>\n"
            "NOTES: <one sentence on what it would do and what real, owner-supplied data it would read>\n"
            "CODE:\n<a short candidate Python function implementing it - pure function, no network "
            "calls, no secrets, reads only arguments passed to it - in the style of "
            "core/apex/agents_impl.py>",
            text, max_tokens=400)
    except Exception:
        budget.release(key)
        raise
    budget.settle(key, 1)
    name, notes, code = "UNNAMED", "", ""
    if "CODE:" in raw:
        head, code = raw.split("CODE:", 1)
    else:
        head, code = raw, ""
    for line in head.splitlines():
        if line.upper().startswith("NAME:"):
            name = line.split(":", 1)[1].strip()[:80] or "UNNAMED"
        elif line.upper().startswith("NOTES:"):
            notes = line.split(":", 1)[1].strip()[:500]
    return {"capability_name": name, "draft_notes": notes, "draft_code": code.strip()[:2000]}


def recurring_gaps(ledger, min_count: int = 3) -> list:
    """Phase D's reminder trigger (SUPERIOR_OS_PLAN_20261113.md): real counts of IDENTICAL
    repeated unmet requests, read from the existing capability_gap fact history - never an
    automatic proposal, only a count-based nudge that the same gap keeps recurring and the
    pending draft (if one was already proposed) is worth reviewing. Matching is exact-text
    only - no fuzzy/semantic matching, no extra LLM call - so this under-counts paraphrased
    repeats; that limitation is deliberate, not hidden."""
    history = factstore.fact_history(ledger, "owner", "capability_gap", limit=500)
    counts: dict = {}
    for h in history:
        counts[h["object"]] = counts.get(h["object"], 0) + 1
    return sorted([{"text": text, "count": n} for text, n in counts.items() if n >= min_count],
                  key=lambda r: -r["count"])


def propose(ledger, gateway, budget, text: str) -> dict:
    """Logs the gap as a fact, drafts the capability, submits it as a PENDING/DEFERRED proposal.
    Returns {"fact_id", "proposal_id", "state"}. Never writes a .py file, never executes the
    draft code, never auto-approves - identical gate as every other proposal kind."""
    now = time.time()
    fact_id = factstore.assert_fact(ledger, "owner", "capability_gap", text, "voice:unmet_request", now=now)
    draft = draft_capability(budget, text)
    payload = {"capability_name": draft["capability_name"], "trigger_text": text[:500],
               "draft_code": draft["draft_code"], "draft_notes": draft["draft_notes"]}
    proposal_id = identifier(f"capability-{hashlib.sha256(text.encode()).hexdigest()[:16]}")
    state = gateway.submit(proposal_id, "opportunity", "capability_proposal", "agent:capability-proposer",
                            payload, [f"fact:{fact_id}"],
                            commentary="DRAFT ONLY - not reviewed, tested, or wired in. Owner must write/adopt a real test and capability by hand.")
    return {"fact_id": fact_id, "proposal_id": proposal_id, "state": state}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text", required=True, help="The unmet request, verbatim")
    args = parser.parse_args()

    from apex.google_web import protected_json  # same secret-loading convention as agents_runner.py/worker_loop.py
    from apex.kernel.gateway import DEFAULT_KINDS
    secret = protected_json("/etc/apex/approvals-runtime.json")["approval_secret"].encode()
    with Ledger(ROOT) as ledger:
        budget = Budget(ledger)
        book = ApprovalBook(ledger, secret)
        gateway = ActionGateway(ledger, book, budget,
                                 kinds={**DEFAULT_KINDS, "capability_proposal": CAPABILITY_PROPOSAL_KIND})
        try:
            result = propose(ledger, gateway, budget, args.text)
        except BudgetDenied as exc:
            sys.exit(f"Can't draft a proposal right now - budget denied ({exc}). Nothing was spent.")
        print(f"Logged gap as fact {result['fact_id']}. Proposal {result['proposal_id']} is "
              f"{result['state']} - review it on /console. Nothing has been written, tested, or adopted.")


if __name__ == "__main__":
    main()
