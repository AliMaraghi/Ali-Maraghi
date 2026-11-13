#!/usr/bin/env bash
# Applies today's voice_api.py restore + telemetry endpoint + VRM avatar + Swarm Command Center.
# No new pip/npm packages: @pixiv/three-vrm was already in apex-ui/package.json; voice_api.py adds
# no dependency. Run this yourself on the VPS - it does not run automatically.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/5: offline test suite - abort on any new failure =="
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py | tail -1
read -r -p "Tests look right (0 new failures/errors above the known baseline)? [y/N] " confirm
[[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted - nothing was built or restarted."; exit 1; }

echo "== 2/5: build the frontend (VRM avatar + Swarm Command Center panel) =="
(cd apex-ui && npm run build)

echo "== 3/5: restart apex-voice.service (secure voice_api.py + telemetry) and apex-agents.service (A-2 in roster) =="
sudo systemctl restart apex-voice.service
sudo systemctl restart apex-agents.service
sleep 2
for unit in apex-voice.service apex-agents.service; do
  sudo systemctl is-active --quiet "$unit" && echo "$unit: active" || {
    echo "$unit failed to come up - check: journalctl -u $unit -n 40"; exit 1; }
done

echo "== 4/5: verify voice_api is loopback-only, not world-bound =="
BIND=$(ss -tlnp 2>/dev/null | grep ':8000\b' || true)
echo "$BIND"
if echo "$BIND" | grep -q '0\.0\.0\.0:8000'; then
  echo "FAIL: port 8000 is bound to 0.0.0.0, not 127.0.0.1 - stop and investigate before trusting this deploy."
  exit 1
fi
echo "OK: 8000 is loopback-only."

echo "== 5/5: live smoke check through the real domain =="
curl -s -o /dev/null -w "ui.apexcorelab.uk: %{http_code}\n" https://ui.apexcorelab.uk/ || true
curl -s https://api.apexcorelab.uk/api/agent_telemetry | head -c 300; echo

cat <<'EOF'

Done. What this did NOT do, on purpose:
  - Did not claim a fabricated "ACTIVE" status anywhere: the telemetry endpoint only reports the
    last real completed run and whether a run is due (see scripts/orchestrator.py's
    agent_telemetry() docstring). There is no live-execution signal to show, so none is faked.
  - Did not write to a new/old "swarm_status" table from orchestrator.py - that table's write
    path was the same one swarm_worker.py used to bypass the Ledger's safety discipline earlier
    this session; telemetry reads only from the existing agent_schedule/events tables that
    AgentRunner (core/apex/agents_runtime.py) already writes correctly.
  - Did not touch apex-ui.service's bind (0.0.0.0:8081) or Cloudflare Access - both still open
    items from earlier in this session; this script does not silently resolve them.
EOF
