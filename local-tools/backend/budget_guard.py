"""Minimal, dependency-free daily call cap - so leaving this running overnight can't ring up
an unbounded Anthropic bill. Not the full kernel.budget circuit breaker from the parent
project (no SQLite ledger, no audit trail) - this is a clean, standalone tool, and a plain
JSON counter file is all a personal local app needs.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

COUNTER_PATH = Path(os.environ.get("BUDGET_COUNTER_PATH", "/data/call_counter.json"))
MAX_CALLS_PER_DAY = int(os.environ.get("MAX_CALLS_PER_DAY", "100"))


class BudgetDenied(Exception):
    pass


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def check_and_increment(tool: str) -> None:
    """Raises BudgetDenied if today's call count for ANY tool combined has hit the cap.
    Fails OPEN on a corrupt/missing counter file (reset to zero) rather than blocking forever
    because of one bad write - this is a courtesy limiter, not a security boundary."""
    COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    today = _today()
    try:
        data = json.loads(COUNTER_PATH.read_text()) if COUNTER_PATH.is_file() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0, "by_tool": {}}
    data["count"] = data.get("count", 0)
    if data["count"] >= MAX_CALLS_PER_DAY:
        raise BudgetDenied(f"Daily cap of {MAX_CALLS_PER_DAY} calls reached - set MAX_CALLS_PER_DAY to raise it.")
    data["count"] += 1
    data.setdefault("by_tool", {})[tool] = data["by_tool"].get(tool, 0) + 1
    COUNTER_PATH.write_text(json.dumps(data))
