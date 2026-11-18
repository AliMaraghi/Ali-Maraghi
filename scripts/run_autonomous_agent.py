#!/usr/bin/env python3
"""Daily autonomous briefing: one bounded ReAct run (core/apex/agent_loop.py), written to the Ledger.

Scheduling lives in systemd (deploy/user/apex-briefing.timer, 07:00 Europe/London), not in this
file - this script runs once and exits.

  python3 -B scripts/run_autonomous_agent.py                 # one real run
  python3 -B scripts/run_autonomous_agent.py --set-price     # price the loop's SKU, then exit
  python3 -B scripts/run_autonomous_agent.py --goal "..."    # one run with a different goal

Fails closed: no priced SKU or no cap on pool "core" -> the loop stops at step 1 with
BUDGET_DENIED and that outcome (not a made-up briefing) is what gets recorded. A durable stop
(kill switch) aborts before anything runs. Exit code 0 only when the briefing COMPLETED.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex import agent_loop                                   # noqa: E402
from apex.kernel.budget import Budget                         # noqa: E402
from apex.kernel.memory import Ledger                         # noqa: E402
from apex.kernel.policy import enforce_durable_stop           # noqa: E402

DEFAULT_GOAL = ("First call read_scouts. Then check arXiv for new papers. Then write a short daily "
                "briefing: today's best event and why, the job and money headline the scouts found, and "
                "anything notable in the papers. If a tool fails, say so in one line and move on.")
APPROVALS_CONFIG = "/etc/apex/approvals-runtime.json"         # same file agents_runner.py reads
PRICE_MILLIPENCE_PER_STEP = 2_000                             # same flat 2p/call estimate as voice_api.py


def set_price() -> None:
    with Ledger(ROOT) as ledger:
        Budget(ledger).set_price(agent_loop.PROVIDER, agent_loop.SKU_STEP, PRICE_MILLIPENCE_PER_STEP,
                                 time.time(), "flat per-call estimate, owner-set, not metered per-token")
    print(f"Priced {agent_loop.SKU_STEP} at {PRICE_MILLIPENCE_PER_STEP / 1000}p/step. Worst case per run: "
          f"{agent_loop.MAX_STEPS} steps + dating draft calls, all inside the existing 'core' daily cap.")


def approval_book(ledger):
    """The existing ApprovalBook, or None if its secret is not readable (proposals are then
    refused inside the loop - nothing is queued and nothing is executed)."""
    try:
        from apex.google_web import protected_json
        from apex.kernel.approvals import ApprovalBook
        secret = protected_json(APPROVALS_CONFIG)["approval_secret"].encode()
        return ApprovalBook(ledger, secret)
    except Exception as exc:
        print(f"[agent] approvals unavailable ({type(exc).__name__}); write actions will be refused", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--set-price", action="store_true")
    parser.add_argument("--max-steps", type=int, default=agent_loop.MAX_STEPS)
    args = parser.parse_args()
    if args.set_price:
        set_price()
        return 0
    if not 1 <= args.max_steps <= agent_loop.MAX_STEPS:
        sys.exit(f"--max-steps must be 1..{agent_loop.MAX_STEPS}")

    now = time.time()
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)
        result, key = run_briefing(ledger, args.goal, args.max_steps, now)

    # Counts and status only on stdout/journald - never briefing content (same rule as nightly_run.py).
    print(f"[agent] {result['status']} event={key} steps={len(result['trace'])} "
          f"proposals={len(result['proposals'])} digest={result.get('digest_used', False)}")
    return 0 if result["status"] == "COMPLETED" else 1


def scout_digest(root) -> str:
    """Plain facts from the scouts' own records, used when the planning model does not finish."""
    from apex import scout_common
    events, wealth = scout_common.latest(root, "events") or {}, scout_common.latest(root, "wealth") or {}
    lines = [f"Event: {e.get('title')} ({e.get('start')})" for e in (events.get("picked") or [])[:3]]
    job, alert = wealth.get("job") or {}, wealth.get("alert") or {}
    if job.get("title"):
        lines.append(f"Job: {job['title']}" + (f" at {job['employer']}" if job.get("employer") else ""))
    elif wealth.get("job_status"):
        lines.append(f"Job search: {wealth['job_status']}")
    if alert.get("headline"):
        lines.append(f"Money headline: {alert['headline']} ({alert.get('source', 'source not recorded')})")
    try:
        from apex import spending_rules
        spend = scout_common.latest(root, "spend")
        line = spending_rules.digest(spend)
        if line:
            lines.append(line)
        alert = spending_rules.food_alert(spend, scout_common.load_config(root).get("food_weekly_cap_pence"))
        if alert and alert["exceeded"]:
            lines.append(f"Food ordered in or eaten out, week of {alert['week_start']}: {alert['current_pence'] / 100:.2f} pounds "
                         f"against a weekly limit of {alert['cap_pence'] / 100:.2f} (statement data to {alert['data_through']})")
    except Exception:
        pass
    return "\n".join(lines)


def run_briefing(ledger, goal: str = DEFAULT_GOAL, max_steps: int = agent_loop.MAX_STEPS, now: float | None = None):
    """One daily run: today's mission from the scouts' picks, then the bounded planning loop. If
    the loop does not finish, the briefing still carries the scouts' facts, labelled as such."""
    from apex.agents_research import call_anthropic, load_api_key
    from apex import scout_common, scout_events
    import agents_runner                                      # scripts/agents_runner.py: fetch_public
    import dating_agent                                       # scripts/dating_agent.py: generate_openers

    now = time.time() if now is None else now
    budget = Budget(ledger)
    api_key = load_api_key()
    llm = lambda system, user_text, max_tokens: call_anthropic(api_key, system, user_text, max_tokens=max_tokens)  # noqa: E731
    try:                                                      # 07:00: fresh line status for the morning
        from apex import commute
        scout_common.record(ledger, "commute", commute.run(scout_common.load_config(ROOT), agents_runner.fetch_public, now), now)
    except Exception as exc:
        print(f"[agent] commute skipped: {type(exc).__name__}", file=sys.stderr)
    try:
        scout_common.record(ledger, "mission", scout_events.pick_mission(scout_common.latest(ROOT, "events"), llm, budget, now), now)
    except Exception as exc:
        print(f"[agent] mission skipped: {type(exc).__name__}", file=sys.stderr)
    try:
        from apex import semantic_memory
        memory = semantic_memory.open_if_enabled(ledger.db)   # None unless APEX_LLM_PROVIDER=ollama
    except Exception:
        memory = None
    toolbox = agent_loop.Toolbox(
        root=ROOT, fetch=agents_runner.fetch_public,
        openers=lambda profile: dating_agent.generate_openers(budget, profile), memory=memory, now=now)
    result = agent_loop.run(goal, toolbox, budget, llm=llm, book=approval_book(ledger), max_steps=max_steps)
    if result["status"] != "COMPLETED":
        digest = scout_digest(ROOT)
        if digest:
            result["report"] += "\n\nFrom the scouts' own records (not written by the planning model):\n" + digest
            result["digest_used"] = True
    key = agent_loop.record_briefing(ledger, goal, result, now=now)
    if memory is not None and result["status"] == "COMPLETED":
        try:
            memory.add("briefing", key, f"Daily briefing {time.strftime('%Y-%m-%d', time.gmtime(now))}: {result['report']}")
        except Exception:
            pass

    return result, key


if __name__ == "__main__":
    sys.exit(main())
