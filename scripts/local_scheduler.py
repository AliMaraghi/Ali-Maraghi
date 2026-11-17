#!/usr/bin/env python3
"""Runs the daily briefing at 07:00 Europe/London inside a container (no systemd there).

On the VPS the systemd timer (deploy/user/apex-briefing.timer) does this job instead; do not
run both against the same database.
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE, HOUR = ZoneInfo("Europe/London"), 7


def seconds_until_next_run(now: datetime | None = None) -> float:
    now = now or datetime.now(ZONE)
    target = now.replace(hour=HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    while True:
        wait = seconds_until_next_run()
        print(f"[scheduler] next briefing in {int(wait // 60)} min", flush=True)
        time.sleep(wait)
        code = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "run_autonomous_agent.py")]).returncode
        print(f"[scheduler] briefing run exited with {code}", flush=True)
        time.sleep(60)          # never fire twice inside the same minute


if __name__ == "__main__":
    main()
