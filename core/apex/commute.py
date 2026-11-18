"""Morning line status from Transport for London's open API. Read-only, no key, no model.

One GET to https://api.tfl.gov.uk/Line/<ids>/Status for the lines the owner set in his private
config ("commute_lines"). The result is what TfL published at that moment; nothing is guessed
and no alternative route is invented - a disrupted line carries TfL's own reason text.
"""
from __future__ import annotations

import json
import re
import time

LINE_ID = re.compile(r"[a-z][a-z0-9-]{1,30}")
MAX_LINES = 8


def status_url(lines: list) -> str:
    if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES or not all(isinstance(x, str) and LINE_ID.fullmatch(x) for x in lines):
        raise ValueError("1-8 TfL line ids")
    return "https://api.tfl.gov.uk/Line/" + ",".join(lines) + "/Status"


def run(config: dict, fetch, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    lines = config.get("commute_lines") or []
    if not lines:
        return {"event": "commute", "status": "NO_LINES_SET", "lines": []}
    try:
        data = json.loads(fetch(status_url(lines)))
    except Exception as exc:
        return {"event": "commute", "status": f"UNAVAILABLE:{type(exc).__name__}", "lines": []}
    out = []
    for item in data if isinstance(data, list) else []:
        statuses = item.get("lineStatuses") if isinstance(item, dict) else None
        if not isinstance(statuses, list) or not statuses:
            continue
        worst = min(statuses, key=lambda s: s.get("statusSeverity", 10) if isinstance(s, dict) else 10)
        text = str(worst.get("statusSeverityDescription") or "")[:60]
        out.append({"id": str(item.get("id"))[:40], "name": str(item.get("name"))[:60], "state": text,
                    "good": text == "Good Service", "reason": " ".join(str(worst.get("reason") or "").split())[:300]})
    return {"event": "commute", "status": "OK" if out else "EMPTY", "lines": out, "all_good": bool(out) and all(x["good"] for x in out)}
