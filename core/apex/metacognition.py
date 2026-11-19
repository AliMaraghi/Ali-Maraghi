"""What the system knows about its own reliability, computed from evidence rather than asked of a language model
(a model's self-rated confidence is not calibrated). Also tomorrow's curriculum: concrete tasks derived from what is
stale, blocked, failed or newly possible - each marked as something the system will do itself or needs the owner for."""
from __future__ import annotations


def confidence(gaps: list, agents: list, actions: list) -> dict:
    """0-100. Starts at 100; loses points for stale sources, failed actions and agents that are not really running."""
    stale = [g for g in gaps if g["surprise"] > 0]
    failed = [a for a in actions if a["result"] in ("ERROR", "NO_DATA", "NO_MODEL", "BLOCKED_MISSING_CREDENTIAL")]
    idle = [a for a in agents if a["state"] not in ("AUTONOMOUS_SCAN", "PENDING_APPROVAL")]
    score = 100 - min(40, 6 * len(stale)) - min(30, 10 * len(failed)) - min(30, round(30 * len(idle) / max(len(agents), 1)))
    reasons = ([f"{len(stale)} data source(s) older than they should be: {', '.join(g['source'] for g in stale[:5])}"] if stale else []) + \
              ([f"{len(failed)} task(s) did not succeed this cycle: {', '.join(a['task'] for a in failed[:5])}"] if failed else []) + \
              ([f"{len(idle)} of {len(agents)} agents are not running: {', '.join(a['agent_id'] for a in idle[:8])}"] if idle else [])
    return {"score": max(0, score), "unsure": score < 60, "reasons": reasons}


def curriculum(gaps: list, agents: list, actions: list, property_rec: dict | None, lessons_added: int) -> list:
    tasks = []
    for a in actions:
        if a["result"] in ("ERROR", "NO_DATA", "NO_MODEL"):
            tasks.append({"task": f"Retry '{a['task']}' and record why it failed: {a['detail'][:80]}", "who": "system", "why": "failed this cycle"})
    for g in gaps:
        if g["surprise"] >= 1:
            tasks.append({"task": f"Refresh '{g['source']}' (overdue by {g['surprise']:.1f}x its normal interval)", "who": "system", "why": "stale"})
    for a in agents:
        if a["state"] in ("BLOCKED_MISSING_INPUT", "BLOCKED_MISSING_CREDENTIAL"):
            tasks.append({"task": f"Unblock {a['agent_id']} ({a['name']}): {a['reason'][:90]}", "who": "owner", "why": "blocked"})
        elif a["state"] == "PENDING_APPROVAL":
            tasks.append({"task": f"Decide {a['agent_id']}: {a['reason'][:90]}", "who": "owner", "why": "waiting for you"})
    within = (property_rec or {}).get("within_budget") or []
    if within:
        tasks.append({"task": f"Look at current listings for terraced houses in {', '.join(within[:4])} (average sold price is within budget)", "who": "owner", "why": "new opportunity"})
    if lessons_added:
        tasks.append({"task": f"Check tomorrow whether the {lessons_added} new prompt lesson(s) improved the outputs they target", "who": "system", "why": "self-review"})
    return tasks[:15]
