#!/usr/bin/env python3
"""The OODA worker: Observe -> Orient/Decide -> Act, on a fixed interval, forever (while run as a service). Status: TESTS_NOT_RUN.

  python3 -B scripts/worker_loop.py --once
  python3 -B scripts/worker_loop.py --loop --interval 300        (deploy/production/apex-agents.service runs this)

OBSERVE / ORIENT / DECIDE: delegated to the existing agents (A-1, A-2, A-5, A-8) via agents_runner.cycle(). Each agent reads its
inputs and proposes typed actions through the Action Gateway; nothing here invents a decision procedure beyond that.
ACT: for proposals already APPROVED by the owner in the console (never auto-approved here), call Gateway.execute() once.
For kind "laptop_browser_task" this only ENQUEUES onto the bridge queue; the task still needs the owner's "y" on the laptop
before anything runs there. Budget: the GBP 20/month cap from agents_runner applies; Gateway.execute refuses anything over
cap with BUDGET_CAP_EXCEEDED, and that never stops the free/local agent cycle itself.
Self-evolution: deliberately NOT implemented here. No code is generated, modified or deployed by this loop.

RESTORED 2026-11-13 (second time): this file was found replaced on disk with a stub that ran no
real agent logic - it imported the legacy agents_registry.AGENTS table (mostly SPEC_ONLY),
fabricated "<name> completed cycle" rows for all 18 slots including unimplemented ones, redefined
agent_schedule with an incompatible schema (breaking the real AgentRunner scheduler), and - in its
latest revision - added `subprocess.run(["python3", ".../core/apex/bank_agent.py"])` for A-8,
executing an unreviewed script with a raw Starling bearer-token pattern completely outside the
Action Gateway/Budget/Ledger. The corrupted agent_schedule table was dropped so AgentRunner
recreates the real schema. This is the reviewed version from before any of that, unchanged in
substance (plus the A-2 addition already made earlier this session).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agents_runner as runner                                     # noqa: E402  (reuses its Budget/Gateway/Ledger setup)
from apex.kernel.gateway import GatewayError                       # noqa: E402
from apex.kernel.memory import Ledger                               # noqa: E402
from apex.kernel.policy import enforce_durable_stop                 # noqa: E402


def act_on_approved(gateway, book, domains=("opportunity", "personal")):
    """Execute every APPROVED proposal once. Returns a list of {"id","result"}. Never approves anything itself."""
    acted = []
    for row in book.listing():
        if row["state"] != "APPROVED":
            continue
        try:
            result = gateway.execute(row["id"])
        except GatewayError as exc:
            result = f"ERROR:{exc}"
        acted.append({"id": row["id"], "kind": row["kind"], "result": result})
    return acted


def ooda_cycle():
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)
        secret = runner.protected_json("/etc/apex/approvals-runtime.json")["approval_secret"].encode()
        budget = runner.Budget(ledger)
        budget.set_price("mock", "echo", 0, 0, "built-in zero-cost mock provider (no external call)")
        budget.set_cap("global", "month", runner.MONTHLY_BUDGET_PENCE)
        for pool in ("core", "intelligence", "studio", "retry"):
            budget.set_cap(pool, "month", runner.MONTHLY_BUDGET_PENCE)
        book = runner.ApprovalBook(ledger, secret)
        gateway = runner.ActionGateway(ledger, book, budget)
        # ScientificResearch (A-2) reserves its own LLM spend (see agents_runner.py's own comment
        # on the same line) - stays a no-op until an operator prices it, same zero-budget-by-
        # default guarantee as every other paid call in this project.
        agents = [runner.StrategicIntelligence(), runner.CareerIndustry(), runner.FinancialIntelligence(),
                  runner.HealthLongevity(), runner.EvidenceVerification(ledger), runner.ScientificResearch(budget, ledger)]
        agent_runner = runner.AgentRunner(ledger, gateway, agents, notifier=runner.make_notifier())
        observed = runner.cycle(ledger, agent_runner)           # OBSERVE + ORIENT/DECIDE: agents read inputs and propose
        acted = act_on_approved(gateway, book)                   # ACT: only on what the owner already approved
        return {"observe_decide": observed, "act": acted}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    if args.once == args.loop or not 60 <= args.interval <= 86400:
        sys.exit("Use exactly one of --once / --loop, with 60 <= --interval <= 86400")
    while True:
        try:
            result = ooda_cycle()
            print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **result}), flush=True)
        except PermissionError as exc:
            print(json.dumps({"stopped": str(exc)}), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
