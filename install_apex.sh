#!/usr/bin/env bash
# APEX: switch the EXISTING server install to a local Ollama model, rebuild the UI, restart.
#
# Run as root on the VPS, from the repository, AFTER tonight's patch has been applied:
#   cd /home/apexdev/apex-work && bash install_apex.sh
#
# What it does NOT do, on purpose: no second copy of the code, no change to the firewall, no
# new public port, no `apt upgrade`, no service rewritten to run as root. It stops at the first
# error and only reports success after the backend has actually answered.
set -euo pipefail

REPO="${APEX_REPO:-/home/apexdev/apex-work}"
OWNER="${APEX_OWNER:-apexdev}"
MODEL="${APEX_OLLAMA_MODEL:-qwen3:4b}"
EMBED="${APEX_OLLAMA_EMBED:-bge-m3}"
AS_OWNER=(sudo -u "$OWNER" env PYTHONDONTWRITEBYTECODE=1 APEX_LLM_PROVIDER=ollama
          APEX_OLLAMA_MODEL="$MODEL" APEX_OLLAMA_EMBED="$EMBED")

step() { printf '\n== %s ==\n' "$1"; }
fail() { printf '\nSTOPPED: %s\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run this as root"
[ -d "$REPO/.git" ] || fail "$REPO is not the APEX repository"
[ -f "$REPO/core/apex/local_llm.py" ] || fail "tonight's patch is not applied in $REPO (core/apex/local_llm.py missing)"
id "$OWNER" >/dev/null 2>&1 || fail "user $OWNER does not exist"
cd "$REPO"

step "1/8 Back up the database before touching anything"
if [ -f runtime/kernel.sqlite3 ]; then
  "${AS_OWNER[@]}" python3 -B scripts/backup_sqlite.py
else
  echo "No runtime/kernel.sqlite3 yet - nothing to back up."
fi

step "2/8 Memory check"
TOTAL_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
echo "RAM: ${TOTAL_MB} MB. Model: ${MODEL}."
[ "$TOTAL_MB" -ge 7000 ] || fail "less than 7 GB RAM; pick a smaller model (APEX_OLLAMA_MODEL=qwen3:1.7b) and re-run"

step "3/8 Install Ollama (listens on 127.0.0.1 only) and pull the models"
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable --now ollama
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:11434/api/version >/dev/null || fail "Ollama did not start (journalctl -u ollama -n 40)"
ollama pull "$MODEL"
ollama pull "$EMBED"

step "4/8 Point the existing services at the local model"
for unit in apex-voice.service apex-agents.service; do
  if systemctl cat "$unit" >/dev/null 2>&1; then
    install -D -m 0644 deploy/production/apex-local-llm.conf "/etc/systemd/system/${unit}.d/local-llm.conf"
    sed -i "s|^Environment=APEX_OLLAMA_MODEL=.*|Environment=APEX_OLLAMA_MODEL=${MODEL}|; s|^Environment=APEX_OLLAMA_EMBED=.*|Environment=APEX_OLLAMA_EMBED=${EMBED}|" \
      "/etc/systemd/system/${unit}.d/local-llm.conf"
    echo "configured $unit"
  else
    echo "skipped $unit (not installed on this server)"
  fi
done
systemctl daemon-reload

step "5/8 Build the UI as ${OWNER} (fixes the root-owned dist/ problem at its cause)"
chown -R "$OWNER:$OWNER" apex-ui .git
sudo -u "$OWNER" bash -c 'cd apex-ui && npm ci && npm run build'

step "6/8 Budget: local inference has no per-call cost"
"${AS_OWNER[@]}" python3 -B scripts/serve_container.py --price-only

step "7/8 Restart, index existing conversations, schedule the 07:00 briefing"
for unit in apex-voice.service apex-agents.service; do
  systemctl cat "$unit" >/dev/null 2>&1 && systemctl restart "$unit"
done
sleep 3
systemctl is-active --quiet apex-voice.service || fail "apex-voice.service did not come up (journalctl -u apex-voice -n 40)"
"${AS_OWNER[@]}" python3 -B scripts/voice_api.py --reindex-memory || echo "WARNING: memory indexing failed; chat still works, recall falls back to keywords."
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
sudo -u "$OWNER" install -D -m 0644 deploy/user/apex-briefing.service "$OWNER_HOME/.config/systemd/user/apex-briefing.service"
sudo -u "$OWNER" install -D -m 0644 deploy/user/apex-briefing.timer "$OWNER_HOME/.config/systemd/user/apex-briefing.timer"
loginctl enable-linger "$OWNER"
if systemctl --user -M "${OWNER}@" daemon-reload && systemctl --user -M "${OWNER}@" enable --now apex-briefing.timer; then
  echo "briefing timer enabled"
else
  echo "WARNING: could not enable the briefing timer automatically; everything else is unaffected."
fi

step "8/8 Live check (the first reply loads the model and can take a few minutes on CPU)"
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/dashboard || true)
[ "$CODE" = "200" ] || fail "dashboard returned HTTP ${CODE:-none}"
REPLY=$(curl -s --max-time 600 -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' -d '{"text":"Reply with the single word: ready"}' || true)
echo "chat reply: ${REPLY:-<none>}"
echo "$REPLY" | grep -q '"reply"' || fail "the local model did not answer; see: journalctl -u apex-voice -n 40 ; journalctl -u ollama -n 40"
if ss -tlnp 2>/dev/null | grep -q '0\.0\.0\.0:11434\|\[::\]:11434'; then
  fail "Ollama is listening on a public interface - stop and fix before continuing"
fi

printf '\nDONE. Backend answered from the local model (%s). UI: https://ui.apexcorelab.uk\n' "$MODEL"
echo "Not changed by this script: firewall, Cloudflare, the UI server's port, any secret."
