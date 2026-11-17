#!/usr/bin/env python3
"""One bounded evolution-lab run. Off unless ENABLE_EVOLUTION_SANDBOX=true.

Tries a handful of seeded weight mutations in the sandbox, logs them to evolution_log, and if
the best one clears the gate raises ONE approval proposal (plus a link-only Telegram notice
when Telegram is configured). It never edits target_heuristics.py. Prints status only.

  ENABLE_EVOLUTION_SANDBOX=true python3 -B scripts/run_evolution.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex.evolution import config, promote_gate          # noqa: E402
from apex.kernel.memory import Ledger                     # noqa: E402
from apex.kernel.policy import enforce_durable_stop       # noqa: E402


def main() -> int:
    if not config.enabled():
        print(json.dumps({"status": "DISABLED", "flag": config.FLAG}))
        return 0
    import agents_runner                                  # make_notifier: existing link-only Telegram notice
    import run_autonomous_agent
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)                      # the existing kill switch stops this too
        book = run_autonomous_agent.approval_book(ledger)
        if book is None:
            print(json.dumps({"status": "APPROVALS_UNAVAILABLE"}))
            return 1
        base_notify = agents_runner.make_notifier()
        notify = (lambda proposal_id: base_notify(proposal_id, "evolution-promote")) if base_notify else None
        print(json.dumps(promote_gate.run_generation(ledger, book, int(time.time()) // 86400, notify)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
