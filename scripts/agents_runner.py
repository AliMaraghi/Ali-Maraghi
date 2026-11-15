#!/usr/bin/env python3
"""Run the local agents once or on an interval (default 300 s). Agents propose; humans approve in the console; nothing executes here.

  python3 -B scripts/agents_runner.py --once
  python3 -B scripts/agents_runner.py --loop --interval 300        (the packaged unit deploy/production/apex-agents.service does this)
Uses the existing local journal (runtime/kernel.sqlite3), the approvals secret in /etc/apex/approvals-runtime.json and the existing Budget/Gateway. Optional Telegram link-only notices when
APEX_TELEGRAM_TOKEN_FILE (private 0600 file) and APEX_TELEGRAM_CHAT_ID are set. No Redis/PostgreSQL: the system's stores are the SQLite journal.
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex import agents_governing, private_token, rss, telegram_bot    # noqa: E402
from apex.agents_impl import CareerIndustry, EvidenceVerification, FinancialIntelligence, HealthLongevity, SocialRelational, StrategicIntelligence      # noqa: E402
from apex.agents_research import ScientificResearch                     # noqa: E402
from apex.agents_runtime import AgentContext, AgentRunner               # noqa: E402
from apex.google_web import protected_json                              # noqa: E402
from apex.kernel.approvals import ApprovalBook                          # noqa: E402
from apex.kernel.budget import Budget                                   # noqa: E402
from apex.kernel.gateway import ActionGateway                           # noqa: E402
from apex.kernel.memory import Ledger                                   # noqa: E402
from apex.kernel import observability                                   # noqa: E402
from apex.kernel.policy import enforce_durable_stop                     # noqa: E402
from apex.sources import public_http                                    # noqa: E402

CONSOLE = "https://console.apexcorelab.uk"
MONTHLY_BUDGET_PENCE = 2000   # GBP 20.00; free/local agents (A-1, A-5, A-8) spend nothing against this cap


def fetch_public(url):
    result = public_http.fetch(url)
    if "error" in result:
        raise RuntimeError(result["error"])
    return base64.b64decode(result["body_b64"])


def make_notifier():
    path, chat = os.environ.get("APEX_TELEGRAM_TOKEN_FILE"), os.environ.get("APEX_TELEGRAM_CHAT_ID")
    if not path or not chat:
        return None
    token, chat_id = private_token.load(path), int(chat)

    def notify(proposal_id, kind):
        text = telegram_bot.approval_notification(proposal_id, kind.replace("_", " "), "within 24 hours", CONSOLE)
        telegram_bot.send_message(token, chat_id, text, telegram_bot.live_transport, {chat_id})
    return notify


def cycle(ledger, runner):
    now = time.time()
    ctx = AgentContext(now=now, today=time.strftime("%Y-%m-%d", time.gmtime(now)), inbox=ROOT / "runtime" / "inbox",
                       rules=ROOT / "runtime" / "rules", fetch=fetch_public)
    return runner.run_once(ctx)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--include-frozen", action="append", default=[],
                         help="Explicitly run a frozen system anyway (see docs/FROZEN_SYSTEMS.md); "
                              "repeatable. Logged on every use.")
    args = parser.parse_args()
    if args.once == args.loop or not 60 <= args.interval <= 86400:
        sys.exit("Use exactly one of --once / --loop, with 60 <= --interval <= 86400")
    secret = protected_json("/etc/apex/approvals-runtime.json")["approval_secret"].encode()
    while True:
        with Ledger(ROOT) as ledger:
            try:
                enforce_durable_stop(ledger)
                budget = Budget(ledger)
                budget.set_price("mock", "echo", 0, 0, "built-in zero-cost mock provider (no external call)")
                budget.set_cap("global", "month", MONTHLY_BUDGET_PENCE)
                for pool in ("core", "intelligence", "studio", "retry"):
                    budget.set_cap(pool, "month", MONTHLY_BUDGET_PENCE)
                gateway = ActionGateway(ledger, ApprovalBook(ledger, secret), budget)
                # ScientificResearch (A-2) needs budget+ledger (it reserves its own LLM spend; see
                # agents_research.py) - unlike the other three it is NOT free. It stays a no-op
                # (confidence 0.0, no proposal) until an operator runs
                # `python3 core/apex/agents_research.py --set-price-millipence N --set-daily-cap-pence N`
                # once - zero-budget-by-default is untouched by adding it here.
                agent_factories = {
                    "strategic_intelligence": lambda: StrategicIntelligence(),
                    "career_industry": lambda: CareerIndustry(),
                    "financial_intelligence": lambda: FinancialIntelligence(ledger),
                    "health_longevity": lambda: HealthLongevity(),
                    "evidence_verification": lambda: EvidenceVerification(ledger),
                    "social_relational": lambda: SocialRelational(),
                    "scientific_research": lambda: ScientificResearch(budget, ledger),
                }
                active_names, skipped = agents_governing.select_active(agent_factories, args.include_frozen)
                for name, reason in skipped.items():
                    print(json.dumps({"skipped_frozen": name, "reason": reason}), flush=True)
                for name in args.include_frozen:
                    if name in agents_governing.FROZEN:
                        print(json.dumps({"override_frozen": name, "reason": agents_governing.FROZEN[name]}), flush=True)
                agents = [agent_factories[name]() for name in active_names]
                runner = AgentRunner(ledger, gateway, agents, notifier=make_notifier())
                start = time.time()
                try:
                    runs = cycle(ledger, runner)
                    ok = True
                except Exception:
                    runs, ok = [], False
                    raise
                finally:
                    observability.record_run(ROOT / "runtime" / "observability.jsonl",
                                             [r["agent"] for r in runs], ok, (time.time() - start) * 1000)
                print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": runs}), flush=True)
            except PermissionError as exc:
                observability.record_run(ROOT / "runtime" / "observability.jsonl", [], False, 0.0)
                print(json.dumps({"stopped": str(exc)}), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
