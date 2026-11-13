#!/usr/bin/env bash
# Deploys today's four additions: A-2 wired into the real worker loop, the Voice->A-2 research
# queue bridge in orchestrator.py, and scripts/mcp_adapter.py (stdio-only, not mounted anywhere).
#
# Deliberately small: no new pip package is installed (no langgraph, no mcp SDK, no uvicorn -
# every new file reuses what's already installed, same reasoning as the rest of this repo), no
# DNS/Cloudflare Access change, no new systemd unit, no port is opened or rebound. The two
# services this run actually restarts (apex-agents, apex-console) already exist; this script
# does not create any new ones.
#
# Run this yourself on the VPS (not run automatically by anyone else):
#   bash deploy_v4.4.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/4: git status (should show only today's reviewed files - stop and look if not) =="
git status --short

echo "== 2/4: offline test suite - abort on any new failure =="
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py | tail -1
echo "Expected: 1 failure + 13 errors (the pre-existing, already-diagnosed console_server.py/"
echo "test_dev_config regression) and nothing else. If that number is different, STOP and look"
echo "before continuing - do not restart services against a result you have not read."
read -r -p "Tests matched the expected baseline above? [y/N] " confirm
[[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted - nothing was restarted."; exit 1; }

echo "== 3/4: restart apex-agents.service (picks up A-2 in the roster; see scripts/worker_loop.py) =="
sudo systemctl restart apex-agents.service
sleep 2
sudo systemctl is-active --quiet apex-agents.service && echo "apex-agents.service: active" || {
  echo "apex-agents.service failed to come up - check: journalctl -u apex-agents.service -n 40"; exit 1; }

echo "== 4/4: apex-console.service - only restart if it is not already active =="
if sudo systemctl is-active --quiet apex-console.service; then
  echo "apex-console.service already active - leaving it alone (nothing in today's change touches it)."
else
  sudo systemctl restart apex-console.service
  sleep 2
  sudo systemctl is-active --quiet apex-console.service && echo "apex-console.service: active" || {
    echo "apex-console.service failed - check: journalctl -u apex-console.service -n 40"; exit 1; }
fi

cat <<'EOF'

Done. What this did NOT do, on purpose:
  - Did not price or cap A-2's LLM spend. It stays a safe no-op (confidence 0.0, no proposal)
    until you run:
      python3 core/apex/agents_research.py --set-price-millipence <N> --set-daily-cap-pence <N>
    and add at least one topic to runtime/inbox/research_topics.json, e.g.:
      [{"topic": "example topic", "status": "pending"}]
  - Did not mount scripts/mcp_adapter.py anywhere network-reachable. It only speaks stdio; wiring
    it into Claude Desktop's extension UI (which spawns it as a local subprocess) is the next,
    separate, manual step - no bash command does that for you.
  - Did not touch apex-ui.service / apex-voice.service / Cloudflare Access / DNS.
EOF
