#!/usr/bin/env bash
# ONE-SHOT installer: hash-verify + install apex-bridge/apex-agents (by calling the ALREADY-REVIEWED owner_handoff.sh,
# never a forked copy of it), then prompt for a Telegram bot token (hidden) and chat ID and wire them to apex-agents
# as a private systemd drop-in. Run once:
#   sudo bash /home/apexdev/apex-work/scripts/install_master.sh
# It does NOT touch Cloudflare or create the bridge key - those still need your browser (console.apexcorelab.uk/bridge
# and one.dash.cloudflare.com), because this session has no access to either.
set -Eeuo pipefail
umask 022
REPO=/home/apexdev/apex-work
TOKEN_FILE=/etc/apex/telegram-token
DROPIN_DIR=/etc/systemd/system/apex-agents.service.d
DROPIN=$DROPIN_DIR/telegram.conf
TOKEN_RE='^[0-9]{3,20}:[A-Za-z0-9_-]{20,128}$'
CHAT_RE='^-?[0-9]{1,20}$'

say() { printf '\n== %s\n' "$*"; }
die() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run with sudo"
cd "$REPO"

say "1/3 Verify the reviewed files, then install apex-bridge and apex-agents (via the existing owner_handoff.sh, unchanged)"
printf '%s  %s\n' \
  c0a1c8182d5b3c5e806608e2174a3df0ea0053b9e59272f6f338c6ebc5a35195 deploy/production/install.py \
  3fe16e44dbe729e3c0a6d448b559fe40b1687d52d6c97edec2290002125b88af scripts/owner_handoff.sh \
  277dceaa02401753eed94dee4fce84bf02e93f1dcbb5ff04fb3563d7b1c36b93 deploy/production/apex-bridge.service \
  321a6483c0ca2194731cd24bf0d9d1c5230fff3b78603e48c7f4da6817fc49b6 deploy/production/apex-agents.service \
  | sha256sum -c - || die "a reviewed file changed; re-check before continuing"
bash scripts/owner_handoff.sh services

say "2/3 Telegram bot token and chat ID (create the bot with @BotFather on Telegram first if you have not already)"
if [ -f "$TOKEN_FILE" ]; then
  echo "A token file already exists at $TOKEN_FILE."
  read -r -p "Type REPLACE to overwrite it with a new token, or press Enter to keep the existing one: " confirm
else
  confirm="REPLACE"
fi
if [ "${confirm:-}" = "REPLACE" ]; then
  read -r -s -p "Telegram bot token (hidden, from @BotFather): " token; echo
  [[ "$token" =~ $TOKEN_RE ]] || die "that does not look like a bot token (digits : letters/digits/_/-, 20-128 chars)"
  install -d -m 0755 -o root -g root /etc/apex
  fd_tmp="$(mktemp /etc/apex/.telegram-token.XXXXXX)"
  printf '%s' "$token" > "$fd_tmp"
  chown apexdev:apexdev "$fd_tmp"
  chmod 0600 "$fd_tmp"
  mv -f "$fd_tmp" "$TOKEN_FILE"
  unset token
  echo "   token stored at $TOKEN_FILE (apexdev:apexdev, mode 600); not shown again"
fi
read -r -p "Telegram chat ID (from https://api.telegram.org/bot<token>/getUpdates -> \"chat\":{\"id\":...}): " chat_id
[[ "$chat_id" =~ $CHAT_RE ]] || die "chat ID must be an integer"

say "3/3 Wire the token/chat ID into apex-agents.service and restart"
install -d -m 0755 -o root -g root "$DROPIN_DIR"
cat > "$DROPIN" <<EOF2
[Service]
Environment=APEX_TELEGRAM_TOKEN_FILE=$TOKEN_FILE
Environment=APEX_TELEGRAM_CHAT_ID=$chat_id
EOF2
chmod 0644 "$DROPIN"
systemctl daemon-reload
systemctl restart apex-agents.service

say "Checks"
systemctl is-active apex-console.service apex-worker.service apex-bridge.service apex-agents.service apex-legal.service
curl -fsS -m 5 http://127.0.0.1:8770/bridge/health >/dev/null && echo "bridge endpoint: ok" || echo "bridge endpoint: NOT reachable yet"

echo
echo "SUCCESS: services installed and running; Telegram wired to apex-agents."
echo "Still needed (your browser only, this script cannot do these):"
echo "  - Cloudflare: route apexcorelab.uk/bridge -> HTTP 127.0.0.1:8770 (one.dash.cloudflare.com)"
echo "  - Bridge key: create it at https://console.apexcorelab.uk/bridge, then run laptop_agent.py on your laptop"
