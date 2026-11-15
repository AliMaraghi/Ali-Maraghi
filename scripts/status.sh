#!/usr/bin/env bash
# Human-readable observability status (Phase 3, mission 2026-11-15). No HTTP server - a JSON
# output is what was asked for; this prints it both raw and human-readable.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHONPATH="$ROOT/core" python3 -B -c "
from pathlib import Path
from apex.kernel import observability
s = observability.status(Path('$ROOT/runtime/observability.jsonl'))
import json
print(json.dumps(s))
print()
print(f\"uptime_days:    {s['uptime_days']}\")
print(f\"last_run:       {s['last_run']}\")
print(f\"runs_total:     {s['runs_total']}\")
print(f\"runs_succeeded: {s['runs_succeeded']}\")
print(f\"runs_failed:    {s['runs_failed']}\")
"
