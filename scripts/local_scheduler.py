#!/usr/bin/env python3
"""Container scheduler (no systemd there): daily briefing at 07:00 Europe/London, and the
Opportunity Scouts every 4 hours at :20.

On the VPS the systemd timers in deploy/user/ do this job instead; do not run both against
the same database.
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("Europe/London")
JOBS = {
    "briefing": ("run_autonomous_agent.py", [(7, 0)]),
    "scouts": ("run_scouts.py", [(h, 20) for h in range(0, 24, 4)]),
}


def next_run(slots: list, now: datetime) -> datetime:
    candidates = []
    for day in (0, 1):
        for hour, minute in slots:
            when = (now + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if when > now:
                candidates.append(when)
    return min(candidates)


def seconds_until_next_run(now: datetime | None = None) -> tuple:
    now = now or datetime.now(ZONE)
    name, when = min(((n, next_run(slots, now)) for n, (_, slots) in JOBS.items()), key=lambda item: item[1])
    return name, (when - now).total_seconds()


def main() -> None:
    while True:
        name, wait = seconds_until_next_run()
        print(f"[scheduler] next: {name} in {int(wait // 60)} min", flush=True)
        time.sleep(wait + 1)
        code = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / JOBS[name][0])]).returncode
        print(f"[scheduler] {name} exited with {code}", flush=True)
        time.sleep(60)          # never fire twice inside the same minute


if __name__ == "__main__":
    main()
