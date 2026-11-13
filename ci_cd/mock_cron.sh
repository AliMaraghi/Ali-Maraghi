#!/usr/bin/env bash
# DEV-ONLY load loop: runs worker_loop.py --once every N seconds in THIS shell, in the foreground, as the current user.
# Not installed anywhere, not a systemd/cron/Docker service, no sudo, no production effect. Stop with Ctrl-C.
#   bash ci_cd/mock_cron.sh [interval_seconds] [iterations]
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
interval="${1:-60}"
iterations="${2:-0}"   # 0 = run until Ctrl-C
[[ "$interval" =~ ^[0-9]+$ ]] && [ "$interval" -ge 1 ] || { echo "interval must be a positive integer" >&2; exit 1; }
[[ "$iterations" =~ ^[0-9]+$ ]] || { echo "iterations must be a non-negative integer" >&2; exit 1; }
echo "mock_cron: running 'python3 -B scripts/worker_loop.py --once' every ${interval}s (dev-only; not a real schedule)"
count=0
while :; do
  count=$((count + 1))
  echo "--- cycle $count @ $(date -u +%H:%M:%SZ) ---"
  PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/worker_loop.py --once || echo "cycle $count: worker_loop exited non-zero"
  [ "$iterations" != "0" ] && [ "$count" -ge "$iterations" ] && break
  sleep "$interval"
done
