#!/usr/bin/env python3
"""Dating message assistant: paste a profile's text, get 3 respectful draft openers. Nothing else.

No Playwright, no browser, no login to any dating platform, no scraping - this only ever reads
text YOU paste on stdin/argv and prints text to the terminal. The owner copies whichever draft
(if any) they want and sends it themselves, from their own device, inside the dating app. Nothing
here ever touches a dating platform's network, account, or ToS surface.

Budget-gated the same way as A-2/the Twitter drafts (reserve/settle, zero-budget-by-default - see
core/apex/agents_research.py's _spend() for the pattern this reuses). Nothing is stored long-term:
the pasted profile text is processed in memory for this one call and discarded, consistent with
"no third-party dossiers" (docs/apex_status/COMPANION_PRESENCE_ADDENDUM_20261113.md section 9) -
it is someone else's text, not the owner's own data.

Usage:
  python3 scripts/dating_agent.py --set-price-millipence 100 --set-daily-cap-pence 50   (once)
  python3 scripts/dating_agent.py "<paste the profile text here>"
  echo "<profile text>" | python3 scripts/dating_agent.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.agents_research import call_anthropic, load_api_key, ResearchPipelineError  # noqa: E402
from apex.kernel.budget import Budget, BudgetDenied                                    # noqa: E402
from apex.kernel.memory import Ledger                                                  # noqa: E402

PROVIDER, SKU = "anthropic", "dating-draft-step"
MAX_PROFILE_CHARS = 2000
TONE = ("Write 3 short, unique, respectful opening messages for a dating-app profile, based only "
        "on what the profile text below actually says - no generic pickup lines, no fabricated "
        "shared interests, nothing that assumes consent to anything beyond a first message. "
        "Number them 1/2/3, one line each.")


def generate_openers(budget: Budget, profile_text: str) -> str:
    profile_text = profile_text.strip()[:MAX_PROFILE_CHARS]
    if not profile_text:
        raise ValueError("Profile text is empty")
    key = f"dating.{int(time.time() * 1000)}"
    budget.reserve(key, "core", PROVIDER, SKU, 1)
    try:
        api_key = load_api_key()
        result = call_anthropic(api_key, TONE, f"Profile:\n{profile_text}", max_tokens=200)
    except ResearchPipelineError:
        budget.release(key)
        raise
    budget.settle(key, 1)
    return result


def set_price_and_cap(ledger_root: Path, price_millipence: int | None, cap_pence: int | None):
    with Ledger(ledger_root) as ledger:
        budget = Budget(ledger)
        if price_millipence is not None:
            budget.set_price(PROVIDER, SKU, price_millipence, time.time(),
                              "flat per-call estimate, owner-set, not metered per-token")
            print(f"Price set: {price_millipence/1000}p/call for {PROVIDER}:{SKU}")
        if cap_pence is not None:
            budget.set_cap("core", "day", cap_pence)
            print(f"Daily cap set: {cap_pence}p/day on pool 'core' (shared with other core-pool spenders)")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("profile_text", nargs="?", default=None)
    parser.add_argument("--set-price-millipence", type=int, default=None)
    parser.add_argument("--set-daily-cap-pence", type=int, default=None)
    args = parser.parse_args()

    if args.set_price_millipence is not None or args.set_daily_cap_pence is not None:
        set_price_and_cap(ROOT, args.set_price_millipence, args.set_daily_cap_pence)
        return

    text = args.profile_text if args.profile_text is not None else sys.stdin.read()
    with Ledger(ROOT) as ledger:
        budget = Budget(ledger)
        try:
            print(generate_openers(budget, text))
        except BudgetDenied as exc:
            print(f"BUDGET_DENIED: {exc} - run with --set-price-millipence/--set-daily-cap-pence first", file=sys.stderr)
            sys.exit(1)
        except (ValueError, ResearchPipelineError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
