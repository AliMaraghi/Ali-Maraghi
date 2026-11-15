"""Observability (mission 2026-11-15, Phase 3 - the design debt named in this session's own
architecture proposal: "zero uptime measured" was identified as a gap, not a feature to add
later). Tracks every agents_runner.py --once invocation: timestamp, systems run, success/fail,
duration. Writes to a JSON-lines file OUTSIDE the fact ledger - the fact DB is for facts
(assert_fact/assert_signed_fact), not for run telemetry; mixing the two was never asked for and
would make the fact chain's hash-chain verification depend on run-timing noise.

Honest by construction: uptime_since_first_run_days is computed from the first ACTUAL recorded
run, not from install date or any assumed baseline. A system with one run reports ~0 days. A
system that has never run reports runs_total=0 and uptime_days=0 - never fabricated, never
smoothed, never "assume always up"."""
from __future__ import annotations

import json
import time
from pathlib import Path

EMPTY_STATUS = {"uptime_days": 0.0, "last_run": None, "runs_total": 0, "runs_succeeded": 0, "runs_failed": 0}


def record_run(path: Path, systems_run, success: bool, duration_ms: float, now: float | None = None) -> dict:
    """Appends one JSON-lines record. Returns the record written (for the caller to log/print)."""
    now = time.time() if now is None else now
    record = {"ts": now, "systems_run": list(systems_run), "success": bool(success),
              "duration_ms": round(float(duration_ms), 3)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def status(path: Path, now: float | None = None) -> dict:
    """Reads the full observability file and reports honestly. Never raises on a missing or
    empty file - that is simply a system with no run history yet."""
    now = time.time() if now is None else now
    if not path.exists():
        return dict(EMPTY_STATUS)
    runs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    if not runs:
        return dict(EMPTY_STATUS)
    first_ts = min(r["ts"] for r in runs)
    last_ts = max(r["ts"] for r in runs)
    succeeded = sum(1 for r in runs if r["success"])
    return {
        "uptime_days": round((now - first_ts) / 86400.0, 6),
        "last_run": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last_ts)),
        "runs_total": len(runs),
        "runs_succeeded": succeeded,
        "runs_failed": len(runs) - succeeded,
    }
