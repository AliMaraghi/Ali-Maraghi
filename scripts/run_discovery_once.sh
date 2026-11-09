#!/usr/bin/env bash
# Run ONLY after the base Docker Compose core container is confirmed healthy.
# Saves output to the server filesystem, NOT to a chat, LLM, or external service.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p reports/discovery
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="reports/discovery/rde-${stamp}.json"
if docker compose exec -T core python -m apex.discovery.cli --from-db > "$output"; then
  python3 -m json.tool "$output" >/dev/null
  echo "SAVED: $output"
  python3 - "$output" <<'PYTHON'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print('RESULT:',d['status'])
print('PROMOTION:',d['promotion']['decision'])
print('AI API CALLS:',d['api_calls'])
print('AI SPEND USD:',d['billable_ai_spend_usd'])
print('PROVEN SUPERIORITY:',d['empirical_superiority_proven'])
PYTHON
else
  echo "BLOCKED: inspect the local report $output (do not send .env)" >&2
  exit 2
fi
