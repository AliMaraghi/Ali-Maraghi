#!/usr/bin/env python3
"""Runs both Opportunity Scouts once and writes their results to the Ledger.

Scheduled every 4 hours by deploy/user/apex-scout.timer (VPS) or scripts/local_scheduler.py
(Docker). Read-only: fetches public feeds, ranks, records. Prints counts and statuses only.

  python3 -B scripts/run_scouts.py              # one run
  python3 -B scripts/run_scouts.py --set-price  # hosted-API mode only: price the scout SKU
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex import scout_common, scout_events, scout_wealth     # noqa: E402
from apex.kernel.budget import Budget                         # noqa: E402
from apex.kernel.memory import Ledger                         # noqa: E402
from apex.kernel.policy import enforce_durable_stop           # noqa: E402


def _collect_jobs(results: list) -> None:
    """Appends Reed listings (title, employer, place, link) to the inbox file the job agent reads. Deduplicated, newest 200."""
    import json
    path = ROOT / "runtime" / "inbox" / "jobs.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        old = old if isinstance(old, list) else []
        seen = {j.get("url") for j in old if isinstance(j, dict)}
        for r in results:
            if not isinstance(r, dict):
                continue
            url = str(r.get("jobUrl") or "")
            job = {"title": str(r.get("jobTitle") or "")[:200], "company": str(r.get("employerName") or "")[:100],
                   "location": str(r.get("locationName") or "")[:100], "source": "reed", "url": url[:500]}
            if job["title"] and job["company"] and url.startswith("https://") and url not in seen:
                seen.add(url)
                old.append(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(old[-200:]), encoding="utf-8")
    except (OSError, ValueError):
        pass


def _maybe_evolve(now: float) -> None:
    """Once a day, and only while the owner has switched it on (runtime/settings/evolution_on), run ONE bounded evolution
    generation. It can only raise a pending proposal for the owner; it never edits or deploys code."""
    import os, subprocess
    flag, stamp = ROOT / "runtime" / "settings" / "evolution_on", ROOT / "runtime" / "settings" / "evolution_last"
    try:
        if not flag.is_file() or (stamp.is_file() and now - float(stamp.read_text() or 0) < 20 * 3600):
            return
        stamp.write_text(str(now))
        out = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "run_evolution.py")], cwd=ROOT, timeout=120,
                             env={**os.environ, "ENABLE_EVOLUTION_SANDBOX": "true"}, capture_output=True, text=True)
        print(f"[scout] evolution: {(out.stdout or out.stderr).strip()[:200]}")
    except Exception as exc:
        print(f"[scout] evolution skipped: {type(exc).__name__}")


def main() -> int:
    if "--set-price" in sys.argv:
        with Ledger(ROOT) as ledger:
            Budget(ledger).set_price(scout_common.PROVIDER, scout_common.SKU, 2_000, time.time(),
                                     "flat per-call estimate, owner-set, not metered per-token")
        print("Priced scout-step at 2p/call (2 calls per run, 6 runs a day = up to 24p/day).")
        return 0

    from apex.agents_research import call_anthropic, load_api_key
    import agents_runner                                      # scripts/agents_runner.py: fetch_public

    now = time.time()
    config = scout_common.load_config(ROOT)
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)
        budget = Budget(ledger)
        try:
            api_key = load_api_key()
            llm = lambda system, user_text, max_tokens: call_anthropic(api_key, system, user_text, max_tokens=max_tokens)  # noqa: E731
        except Exception:
            llm = None                                        # no model: scouts still run, keyword-ranked
        reed = scout_wealth.reed_key()
        def _reed(keywords, location):
            results = scout_wealth.reed_fetch(reed, keywords, location)
            _collect_jobs(results)                            # A-5 (job agent) reads these from runtime/inbox/jobs.json
            return results
        jobs_fetch = _reed if reed else None

        events = scout_events.run(config, agents_runner.fetch_public, llm, budget, now)
        scout_common.record(ledger, "events", events, now)
        # Each pick becomes a fact the owner can rate (scripts/record_outcome.py). Those ratings
        # are the only data the evolution lab is ever scored against.
        try:
            import json
            from datetime import datetime
            from apex.kernel import facts
            for position, event in enumerate(events["picked"]):
                when = datetime.strptime(event["start"], "%Y-%m-%d %H:%M")
                features = {"text": (event["title"] + " " + event.get("location", "")).lower()[:300],
                            "is_weekend_or_friday_evening": when.weekday() >= 5 or (when.weekday() == 4 and when.hour >= 17)}
                facts.assert_fact(ledger, "owner", f"scout_event_{int(now)}_{position}", json.dumps(features, sort_keys=True),
                                  "scout_events", now=now)
        except Exception:
            pass
        wealth = scout_wealth.run(config, agents_runner.fetch_public, jobs_fetch, llm, budget, now)
        scout_common.record(ledger, "wealth", wealth, now)
        try:                                                  # free: TfL line status for the owner's lines
            from apex import commute
            scout_common.record(ledger, "commute", commute.run(config, agents_runner.fetch_public, now), now)
        except Exception as exc:
            print(f"[scout] commute skipped: {type(exc).__name__}")
        try:                                                  # free, no model call; never stops the run
            from apex import scout_adult_events
            scout_common.record(ledger, "adult", scout_adult_events.run(config, agents_runner.fetch_public, now), now)
        except Exception as exc:
            print(f"[scout] adult events skipped: {type(exc).__name__}")

    _maybe_evolve(now)
    print(f"[scout] events={events['status']} picked={len(events['picked'])} failed_feeds={len(events['feeds_failed'])} "
          f"job={wealth.get('job_status')} alert={wealth.get('alert_status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
