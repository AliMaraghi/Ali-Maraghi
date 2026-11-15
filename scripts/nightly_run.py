#!/usr/bin/env python3
"""Persistent scheduling layer, S1 (brutal-honesty directive, 2026-11-15): the nightly
wrapper a user-level systemd timer (deploy/user/apex-nightly.timer) runs. Runs
agents_runner.py --once, then record_outcome.py --list as a "did anything new get
recorded" check, and logs to runtime/logs/cron-YYYYMMDD.log - COUNTS AND EXIT CODES ONLY,
never fact/proposal CONTENT, so a log file is never itself a data-leak surface. Logs older
than RETENTION_DAYS are rotated (deleted) on every run.

--dry-run: writes exactly ONE log line and runs neither agents_runner.py nor
record_outcome.py - zero proposals executed, zero facts touched. This is what the gate
checks.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
RETENTION_DAYS = 14


def _rotate_logs(log_dir: Path) -> int:
    if not log_dir.is_dir():
        return 0
    cutoff = time.time() - RETENTION_DAYS * 86400
    removed = 0
    for f in log_dir.glob("cron-*.log"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed


def _log_path(log_dir: Path) -> Path:
    today = time.strftime("%Y%m%d", time.gmtime())
    return log_dir / f"cron-{today}.log"


def _log_line(log_dir: Path, message: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = _log_path(log_dir)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp} {message}\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Log one line, run nothing, execute zero proposals")
    parser.add_argument("--root", default=str(DEFAULT_ROOT),
                        help="Repo root (defaults to the real one; tests point elsewhere)")
    args = parser.parse_args()
    root = Path(args.root)
    log_dir = root / "runtime" / "logs"

    removed = _rotate_logs(log_dir)

    if args.dry_run:
        path = _log_line(log_dir, f"DRY_RUN rotated_logs={removed} would_run=agents_runner.py,record_outcome.py "
                         "proposals_executed=0")
        print(f"Logged to {path}")
        return 0

    agents_result = subprocess.run(
        [sys.executable, "-B", str(root / "scripts" / "agents_runner.py"), "--once"],
        capture_output=True, text=True)
    _log_line(log_dir, f"agents_runner_once exit={agents_result.returncode} "
             f"stdout_lines={len(agents_result.stdout.splitlines())} "
             f"stderr_lines={len(agents_result.stderr.splitlines())}")

    outcome_result = subprocess.run(
        [sys.executable, "-B", str(root / "scripts" / "record_outcome.py"), "--list"],
        capture_output=True, text=True)
    fact_count = len([l for l in outcome_result.stdout.splitlines() if l.strip()])
    _log_line(log_dir, f"record_outcome_list exit={outcome_result.returncode} fact_count={fact_count} "
             f"rotated_logs={removed}")

    return 0 if agents_result.returncode == 0 and outcome_result.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
