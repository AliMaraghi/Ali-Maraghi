#!/usr/bin/env python3
"""One content-draft run: at most one draft, queued for the owner's approval. Publishes nothing.

Off unless ENABLE_AUTONOMOUS_SOCIAL=true.
  python3 -B scripts/run_content.py --set-price   # hosted-API mode only (local model costs nothing)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex import content_engine, social_pacing                 # noqa: E402
from apex.kernel.budget import Budget                          # noqa: E402
from apex.kernel.memory import Ledger                          # noqa: E402
from apex.kernel.policy import enforce_durable_stop            # noqa: E402


def main() -> int:
    if "--set-price" in sys.argv:
        with Ledger(ROOT) as ledger:
            Budget(ledger).set_price(content_engine.PROVIDER, content_engine.SKU, 2_000, time.time(), "flat per-call estimate, owner-set")
        print("Priced content-draft at 2p/call (at most 3 calls per run).")
        return 0
    if not social_pacing.enabled():
        print(json.dumps({"status": "DISABLED", "flag": social_pacing.FLAG}))
        return 0
    from apex.agents_research import call_anthropic, load_api_key
    import run_autonomous_agent
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)
        book = run_autonomous_agent.approval_book(ledger)
        if book is None:
            print(json.dumps({"status": "APPROVALS_UNAVAILABLE"}))
            return 1
        key = load_api_key()
        result = content_engine.run_once(ROOT, ledger, book, Budget(ledger),
                                         lambda system, user, max_tokens: call_anthropic(key, system, user, max_tokens))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
