#!/usr/bin/env python3
"""End-to-end check of the whole chain on this machine, with the real model, network and journal.

  python3 -B scripts/e2e_test.py            prints each step and the verdict
  python3 -B scripts/e2e_test.py --json F   also writes the result to F (used by the dashboard)

Six steps, each must really happen: the local model answers in JSON; the event scout records
picks; the wealth scout records a job or a headline; the daily briefing run records a briefing
that carries scout data; the budget engine reports the month's spend; the dashboard API serves
that same briefing. Any failure exits non-zero and names the step. It does real work: one scout
run and one briefing run are recorded in the journal, exactly as the timers would.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

PASS_LINE = "✅ E2E SYSTEM INTEGRATION PASSED."
API = os.environ.get("APEX_API_URL", "http://127.0.0.1:8000")


class StepFailed(Exception):
    pass


def need(condition, message: str):
    if not condition:
        raise StepFailed(message)


def write(path, payload: dict) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    out = parser.parse_args().json
    started = time.time()
    steps: list = []
    write(out, {"state": "running", "started": round(started, 3), "steps": steps})

    from apex import local_llm, scout_common, scout_events, scout_wealth
    from apex.agent_loop import latest_briefing
    from apex.agents_research import call_anthropic, load_api_key
    from apex.kernel.budget import Budget, month_status_from
    from apex.kernel.memory import Ledger
    from apex.kernel.policy import enforce_durable_stop
    import agents_runner
    import run_autonomous_agent

    shared: dict = {}

    def model():
        need(local_llm.enabled(), "APEX_LLM_PROVIDER is not 'ollama' for this process")
        raw = local_llm.complete('Reply with ONE JSON object and nothing else: {"ok": true}', "ping", 40)
        need(json.loads(raw[raw.find("{"):raw.rfind("}") + 1]).get("ok") is True, f"unexpected reply: {raw[:80]!r}")
        return local_llm.model()

    def events(ledger, budget, llm, config, now):
        result = scout_events.run(config, agents_runner.fetch_public, llm, budget, now)
        scout_common.record(ledger, "events", result, now)
        stored = scout_common.latest(ROOT, "events") or {}
        need(stored.get("generated_at") == round(now, 3), "the run was not found in the journal")
        need(stored.get("picked"), f"no events picked (status {result.get('status')}, failed feeds {result.get('feeds_failed')})")
        return f"{len(stored['picked'])} picked from {result.get('considered')} ({result.get('selection')})"

    def wealth(ledger, budget, llm, config, now):
        reed = scout_wealth.reed_key()
        jobs = (lambda keywords, location: scout_wealth.reed_fetch(reed, keywords, location)) if reed else None
        result = scout_wealth.run(config, agents_runner.fetch_public, jobs, llm, budget, now)
        scout_common.record(ledger, "wealth", result, now)
        stored = scout_common.latest(ROOT, "wealth") or {}
        need(stored.get("job") or stored.get("alert"), f"neither a job nor a headline (job {result.get('job_status')}, alert {result.get('alert_status')})")
        return f"job: {result.get('job_status')}, headline: {result.get('alert_status')}"

    def briefing(ledger, now):
        result, key = run_autonomous_agent.run_briefing(ledger, now=now)
        stored = latest_briefing(ROOT) or {}
        need(stored.get("generated_at") == round(now, 3), "the briefing was not found in the journal")
        used_scouts = any(t["action"] == "read_scouts" and t["ok"] for t in result["trace"]) or result.get("digest_used")
        need(used_scouts and stored.get("report"), f"briefing carries no scout data (status {result['status']})")
        shared["briefing_at"] = stored["generated_at"]
        return (f"{result['status']}, {len(result['trace'])} steps"
                + ("; the planning model did not finish, so the scouts' facts were attached directly" if result.get("digest_used") else ""))

    def budget_check(ledger, before):
        after = month_status_from(ledger.db, time.time())
        need(after["spent_pence"] >= before["spent_pence"], "month spend went down")
        need(not after["exhausted"], "the monthly cap is exhausted")
        return f"month spend {before['spent_pence']}p -> {after['spent_pence']}p of {after['cap_pence']}p"

    def dashboard():
        with urllib.request.urlopen(API + "/api/dashboard", timeout=60) as response:
            payload = json.loads(response.read(4_000_000))
        need((payload.get("briefing") or {}).get("generated_at") == shared.get("briefing_at"), "the dashboard is not serving the new briefing")
        return "serves the briefing recorded in step 4"

    failed = None
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)
        budget = Budget(ledger)
        before = month_status_from(ledger.db, started)
        config = scout_common.load_config(ROOT)
        try:
            api_key = load_api_key()
            llm = lambda system, user_text, max_tokens: call_anthropic(api_key, system, user_text, max_tokens=max_tokens)  # noqa: E731
        except Exception:
            llm = None
        plan = [("1 Local model", model),
                ("2 Event scout", lambda: events(ledger, budget, llm, config, time.time())),
                ("3 Wealth scout", lambda: wealth(ledger, budget, llm, config, time.time())),
                ("4 Daily briefing", lambda: briefing(ledger, time.time())),
                ("5 Budget engine", lambda: budget_check(ledger, before)),
                ("6 Dashboard API", dashboard)]
        for name, step in plan:
            began = time.time()
            try:
                detail, ok = step(), True
            except StepFailed as exc:
                detail, ok = str(exc), False
            except Exception as exc:
                detail, ok = f"{type(exc).__name__}: {str(exc)[:160]}", False
            steps.append({"name": name, "ok": ok, "detail": detail, "seconds": round(time.time() - began, 1)})
            print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
            write(out, {"state": "running", "started": round(started, 3), "steps": steps})
            if not ok:
                failed = name
                break
    write(out, {"state": "failed" if failed else "passed", "started": round(started, 3),
                "finished": round(time.time(), 3), "steps": steps})
    if failed:
        print("\n" + "#" * 64 + f"\n#  E2E SYSTEM INTEGRATION FAILED AT STEP {failed}\n" + "#" * 64, file=sys.stderr)
        return 1
    print(PASS_LINE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
