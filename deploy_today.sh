#!/usr/bin/env bash
# End-of-day deploy for: finance/academic/dating voice intents, real telemetry metrics,
# the Executive Dashboard (/api/dashboard + ExecutiveDashboard.jsx), and the price fix for
# finance-strategy-step/twitter-draft-step. Run this yourself on the VPS.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/5: offline test suite - abort on any new failure =="
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py | tail -1
read -r -p "Tests show 0 new failures/errors above the known baseline? [y/N] " confirm
[[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted - nothing was built or restarted."; exit 1; }

echo "== 2/5: price the SKUs voice intents use (idempotent - safe to re-run) =="
python3 scripts/voice_api.py --set-daily-cap-pence 50

echo "== 3/5: build the frontend (Executive Dashboard + CoT UI + VRM avatar) =="
(cd apex-ui && npm run build)

echo "== 4/5: restart services =="
sudo systemctl restart apex-voice.service
sudo systemctl restart apex-agents.service
sleep 2
for unit in apex-voice.service apex-agents.service; do
  sudo systemctl is-active --quiet "$unit" && echo "$unit: active" || {
    echo "$unit failed to come up - check: journalctl -u $unit -n 40"; exit 1; }
done

echo "== 5/5: verify loopback bind and live smoke checks =="
BIND=$(ss -tlnp 2>/dev/null | grep ':8000\b' || true)
echo "$BIND"
if echo "$BIND" | grep -q '0\.0\.0\.0:8000'; then
  echo "FAIL: port 8000 is bound to 0.0.0.0, not 127.0.0.1 - stop and investigate."
  exit 1
fi
curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"text":"run the finance chain"}'; echo
curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"text":"give me the academic news"}'; echo
curl -s http://127.0.0.1:8000/api/dashboard; echo

echo "Done. Run the public verification commands below through the real domain once this looks right."
