#!/usr/bin/env python3
"""APEX OS runner: one real cycle of "look, judge, act, report", repeated in the background.

Each cycle (1) measures how stale every data source is against how often it should refresh (prediction error),
(2) gives every one of the 18 roster agents an honest state with its reason, (3) ranks what to do by expected
utility from the owner's own approve/decline record, (4) does the work that needs no owner input (public trend scan,
script drafts on the local model, refreshing overdue scouts), and (5) writes the whole result to the ledger.
It never publishes, pays, sends or deploys. Runs as a thread inside apex-voice, or standalone:
  python3 -B scripts/apex_os_runner.py --once | --loop
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex import priority, scout_common, trend_scout          # noqa: E402

INTERVAL = 900
EXPECTED = {"events": 4 * 3600, "wealth": 4 * 3600, "commute": 4 * 3600, "adult": 4 * 3600, "trends": 6 * 3600,
            "spend": 14 * 86400, "content_drafts": 24 * 3600}
CREDENTIAL = {"A-5": "Reed job-search key", "A-6": "Gmail connection (sync is switched off)"}
VALUE = {"trends": 3.0, "content_drafts": 4.0, "events": 5.0, "wealth": 6.0, "commute": 2.0, "adult": 3.0, "spend": 6.0}


def _db(root: Path):
    return sqlite3.connect((root / "runtime" / "kernel.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=5)


def approval_counts(root: Path) -> dict:
    """{proposer: [approved_or_executed, declined]} and pending count, from the real proposals table."""
    counts, pending = {}, []
    try:
        db = _db(root)
        for proposer, kind, state, pid in db.execute("SELECT proposer, kind, state, id FROM proposals"):
            c = counts.setdefault(proposer, [0, 0])
            if state in ("APPROVED", "EXECUTED"):
                c[0] += 1
            elif state in ("DENIED", "DECLINED"):
                c[1] += 1
            elif state == "PENDING":
                pending.append({"id": pid, "kind": kind, "proposer": proposer})
        db.close()
    except sqlite3.Error:
        pass
    return {"counts": counts, "pending": pending}


def source_gaps(root: Path, now: float) -> list:
    gaps = []
    for name, expected in EXPECTED.items():
        rec = scout_common.latest(root, name)
        age = now - rec["generated_at"] if rec and rec.get("generated_at") else None
        gaps.append({"source": name, "age_seconds": round(age) if age is not None else None, "expected_seconds": expected,
                     "surprise": priority.surprise(age, expected)})
    return sorted(gaps, key=lambda g: -g["surprise"])


def agent_states(root: Path, approvals: dict) -> list:
    """All 18 roster agents. States: AUTONOMOUS_SCAN, PENDING_APPROVAL, BLOCKED_MISSING_INPUT, BLOCKED_MISSING_CREDENTIAL,
    ERROR, NEVER_RUN, NOT_BUILT. Every non-running state carries the reason."""
    import orchestrator
    from apex import agents_governing, scout_wealth
    telemetry = {a["agent_id"]: a for a in orchestrator.agent_telemetry(root)}
    pending_by = {}
    for p in approvals["pending"]:
        pending_by.setdefault(p["proposer"], []).append(p["id"])
    roster = [(r[0], r[1]) for r in getattr(agents_governing, "_ROLES", [])] or [(k, v["name"]) for k, v in orchestrator._AGENT_META.items()]
    out = []
    for agent_id, name in roster:
        t = telemetry.get(agent_id)
        waiting = [pid for proposer, ids in pending_by.items() if agent_id in proposer for pid in ids]
        if t is None:
            state, reason = "NOT_BUILT", "Specified in the manifesto; no running code yet"
        elif agent_id == "A-5" and scout_wealth.reed_key() is None:
            state, reason = "BLOCKED_MISSING_CREDENTIAL", CREDENTIAL["A-5"]
        elif t["blocked"]:
            state, reason = "BLOCKED_MISSING_INPUT", t["current_task"]
        elif waiting:
            state, reason = "PENDING_APPROVAL", f"{len(waiting)} item(s) waiting for your decision"
        elif t["status"] == "ERROR":
            state, reason = "ERROR", str(t.get("last_error") or "last run failed")[:200]
        elif t["status"] == "NEVER_RUN":
            state, reason = "NEVER_RUN", "Has its input but the agents service has not run it yet"
        else:
            state, reason = "AUTONOMOUS_SCAN", t["current_task"]
        out.append({"agent_id": agent_id, "name": name, "state": state, "reason": reason,
                    "last_run_at": t.get("last_run_at") if t else None})
    return out


def plan(gaps: list, approvals: dict, pulls: dict) -> list:
    """Rank the refreshable sources: expected utility (value x P(owner finds it useful) x urgency) plus a UCB bonus."""
    all_ok = sum(c[0] for c in approvals["counts"].values())
    all_no = sum(c[1] for c in approvals["counts"].values())
    p = priority.posterior(all_ok, all_no)
    total = sum(pulls.values()) or 1
    ranked = []
    for g in gaps:
        eu = priority.expected_utility(VALUE.get(g["source"], 1.0) * (1 + g["surprise"]), p, 0, 0.1)
        bonus = priority.ucb(0.0, pulls.get(g["source"], 0), total)
        ranked.append({"task": g["source"], "expected_utility": round(eu, 2), "explore_bonus": None if bonus == float("inf") else round(bonus, 2),
                       "due": g["surprise"] > 0})
    return sorted(ranked, key=lambda r: (-(r["explore_bonus"] is None), -(r["expected_utility"] + (r["explore_bonus"] or 0))))


def _local_llm():
    try:
        from apex import local_llm
        return (lambda s, u, m: local_llm.complete(s, u, max_tokens=m)) if local_llm.enabled() else None
    except Exception:                                              # noqa: BLE001
        return None


def cycle(root: Path = ROOT, now: float | None = None, fetch=None, llm="auto", run_scouts=True) -> dict:
    from apex.kernel.memory import Ledger
    from apex.kernel.policy import enforce_durable_stop
    now = time.time() if now is None else now
    actions = []
    approvals = approval_counts(root)
    gaps = source_gaps(root, now)
    due = {g["source"] for g in gaps if g["surprise"] > 0}
    if fetch is None:
        import agents_runner
        fetch = agents_runner.fetch_public
    llm = _local_llm() if llm == "auto" else llm
    with Ledger(root) as ledger:
        enforce_durable_stop(ledger)                               # the owner's kill switch stops this loop too
        trends = None
        if "trends" in due:
            trends = trend_scout.scan(fetch)
            scout_common.record(ledger, "trends", trends, now)
            actions.append({"task": "trends", "result": trends["status"], "detail": f"{trends['count']} terms, failed feeds: {trends['feeds_failed'] or 'none'}"})
        if "content_drafts" in due:
            trends = trends or scout_common.latest(root, "trends") or {}
            drafts = [d for d in (trend_scout.draft(llm, t) for t in (trends.get("top") or [])[:3]) if d]
            status = "OK" if drafts else ("NO_MODEL" if llm is None else "NO_DATA")
            scout_common.record(ledger, "content_drafts", {"event": "content_drafts", "status": status, "drafts": drafts}, now)
            actions.append({"task": "content_drafts", "result": status, "detail": f"{len(drafts)} draft(s) stored for your review; nothing is published"})
    if run_scouts and {"events", "wealth"} & due and all(g["surprise"] >= 0.5 for g in gaps if g["source"] in ("events", "wealth")):
        try:                                                       # the 4-hourly timer is late: run the scouts now
            out = subprocess.run([sys.executable, "-B", str(root / "scripts" / "run_scouts.py")], cwd=root, timeout=600,
                                 capture_output=True, text=True, env=dict(os.environ))
            actions.append({"task": "scouts", "result": "OK" if out.returncode == 0 else "ERROR", "detail": (out.stdout or out.stderr).strip()[-200:]})
        except Exception as exc:                                   # noqa: BLE001
            actions.append({"task": "scouts", "result": "ERROR", "detail": type(exc).__name__})
    pulls = {}
    try:
        db = _db(root)
        for name in EXPECTED:
            pulls[name] = db.execute("SELECT COUNT(*) FROM events WHERE event_key LIKE ?", (f"scout.{name}.%",)).fetchone()[0]
        db.close()
    except sqlite3.Error:
        pass
    agents = agent_states(root, approvals)
    payload = {"event": "os_cycle", "status": "OK", "agents": agents, "gaps": source_gaps(root, now), "plan": plan(gaps, approvals, pulls),
               "actions": actions, "pending_approvals": approvals["pending"][:20],
               "summary": {s: sum(1 for a in agents if a["state"] == s) for s in sorted({a["state"] for a in agents})}}
    with Ledger(root) as ledger:
        scout_common.record(ledger, "os", payload, now)
    return payload


def loop(root: Path = ROOT, interval: int = INTERVAL) -> None:
    time.sleep(20)
    while True:
        try:
            out = cycle(root)
            print(f"[os] cycle ok {json.dumps(out['summary'])} actions={[a['task'] + ':' + a['result'] for a in out['actions']]}", flush=True)
        except Exception as exc:                                   # noqa: BLE001 - logged, loop survives
            print(f"[os] cycle failed: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        loop()
    else:
        print(json.dumps(cycle(), indent=1)[:4000])
