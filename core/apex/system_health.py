"""One honest answer to "is each part of APEX alive?", from records and one local probe.

Five checks: the local model answers, the journal opens, and the event scout, wealth scout and
daily briefing each recorded a run recently enough for their own schedule. Nothing is assumed:
a part with no record is red with the reason, never green by default.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from pathlib import Path

from . import local_llm, scout_common

SCOUT_MAX_AGE = 6 * 3600            # runs every 4 hours
BRIEFING_MAX_AGE = 26 * 3600        # runs once a day
E2E_FILE = ("runtime", "e2e_last.json")


def ollama_ok(timeout: float = 2.0) -> tuple[bool, str]:
    if not local_llm.enabled():
        return False, "local model not enabled for this service"
    try:
        with urllib.request.urlopen(local_llm.base_url() + "/api/tags", timeout=timeout) as response:
            names = [m.get("name") for m in json.loads(response.read(200_000)).get("models", [])]
    except Exception as exc:
        return False, type(exc).__name__
    wanted = local_llm.model()
    return (True, wanted) if any(n == wanted or str(n).startswith(wanted + ":") for n in names) else (False, f"{wanted} not installed")


def _age_check(stamp, max_age: float, now: float, extra: str = "") -> dict:
    if not isinstance(stamp, (int, float)):
        return {"ok": False, "last_run": None, "detail": "never run"}
    late = now - stamp > max_age
    return {"ok": not late and not extra, "last_run": stamp, "detail": extra or ("overdue" if late else "")}


def mission(root: Path, now: float | None = None) -> dict | None:
    """Today's mission as last recorded, only while its event has not passed."""
    now = time.time() if now is None else now
    record = scout_common.latest(root, "mission")
    event = record.get("event") if isinstance(record, dict) else None
    if not isinstance(event, dict) or not isinstance(event.get("start"), str):
        return None
    try:
        starts = time.mktime(time.strptime(event["start"], "%Y-%m-%d %H:%M"))
    except ValueError:
        return None
    return {**record} if starts > now - 4 * 3600 else None


def status(root: Path, now: float | None = None, probe=ollama_ok) -> dict:
    now = time.time() if now is None else now
    root = Path(root)
    ai_ok, ai_detail = probe()
    checks = {"local_ai": {"ok": ai_ok, "detail": ai_detail}}
    path = root / "runtime" / "kernel.sqlite3"
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
        try:
            count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            db.close()
        checks["database"] = {"ok": True, "detail": f"{count} journal entries"}
    except Exception as exc:
        checks["database"] = {"ok": False, "detail": type(exc).__name__}
    events, wealth = scout_common.latest(root, "events"), scout_common.latest(root, "wealth")
    checks["event_scout"] = _age_check((events or {}).get("generated_at"), SCOUT_MAX_AGE, now)
    checks["wealth_scout"] = _age_check((wealth or {}).get("generated_at"), SCOUT_MAX_AGE, now)
    try:
        from .agent_loop import latest_briefing
        briefing = latest_briefing(root) or {}
    except Exception:
        briefing = {}
    state = briefing.get("status")
    checks["agent_loop"] = _age_check(briefing.get("generated_at"), BRIEFING_MAX_AGE, now,
                                      "" if state in (None, "COMPLETED") else f"last run: {state}")
    e2e = None
    try:
        e2e = json.loads(root.joinpath(*E2E_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks, "e2e": e2e, "generated_at": round(now, 3)}
