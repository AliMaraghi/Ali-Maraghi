#!/usr/bin/env bash
# APEX kernel deployment - Ubuntu 24.04 VPS, root/sudo required (THIS script, not this dev
# workspace - AGENTS.md's "no root/sudo" rule governs this account's own sandbox, not a
# separate VPS the owner controls and runs this on themselves).
#
# Deploys exactly what exists and is tested today, nothing else:
#   - the hardened sandbox (core/apex/kernel/sandbox.py, with the P-4 fix)
#   - the signed ledger (core/apex/kernel/facts.py - hash chain + external anchor)
#   - the two-layer approval gateway (core/apex/kernel/gateway.py + approvals.py)
#   - observability (core/apex/kernel/observability.py)
#   - the A-17 adversarial evaluation suite (run on startup as an integrity gate)
#   - the behavioral signature module (core/apex/kernel/behavioral_signature.py)
#   - the domain router (core/apex/action_domains/) - Bills active, Email/Calendar staged
#
# NOT deployed because it does not exist: any BFT/Raft consensus, any differential-privacy
# mechanism, any trained Transformer, any Gaussian-splatting/NeRF renderer, any unattended
# daemon that takes real actions. agents_runner.py --once only ever PROPOSES; nothing in
# this codebase auto-executes an approved action without agents_runner.py's own existing
# ActionGateway/ApprovalBook checks, which this script does not touch or weaken.
#
# USAGE (owner runs this themselves, as root, on the target VPS):
#   REPO_SOURCE=/path/or/url  HEALTH_PORT=8080  bash deploy_to_vps.sh
#
# This script does NOT clone from any hardcoded remote - "no remote is authorized" for this
# account per AGENTS.md. REPO_SOURCE must be supplied by the owner: either a path this
# script can `rsync`/`cp -r` from (e.g. after the owner scp's the repo to the VPS), or a
# git remote URL the owner controls and has already authorized. If neither is set, this
# script stops and says so rather than guessing.
set -euo pipefail

APEX_USER="apex"
APEX_HOME="/opt/apex"
APP_DIR="${APEX_HOME}/app"
HEALTH_PORT="${HEALTH_PORT:-8080}"
REPO_SOURCE="${REPO_SOURCE:-}"

log() { printf '[deploy_to_vps] %s\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then
  log "FATAL: must run as root (sudo bash deploy_to_vps.sh). Nothing was changed."
  exit 1
fi

if [ -z "$REPO_SOURCE" ]; then
  log "FATAL: REPO_SOURCE is not set. This script will not guess a git remote."
  log "Set REPO_SOURCE to a local path (already copied onto this VPS) or a git URL you control, then rerun."
  exit 1
fi

# ---- 1. Dependencies -------------------------------------------------------
log "Installing OS packages (python3.12, venv, sqlite3, ufw, fail2ban, git, rsync)..."
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv sqlite3 ufw fail2ban git rsync

# ---- 2. Dedicated unprivileged user ----------------------------------------
if ! id "$APEX_USER" >/dev/null 2>&1; then
  log "Creating dedicated user '$APEX_USER' (no login shell, no sudo)..."
  useradd --system --create-home --home-dir "$APEX_HOME" --shell /usr/sbin/nologin "$APEX_USER"
else
  log "User '$APEX_USER' already exists - not recreating."
fi
mkdir -p "$APP_DIR"

# ---- 3. Code ----------------------------------------------------------------
log "Placing code at $APP_DIR from REPO_SOURCE=$REPO_SOURCE ..."
if [[ "$REPO_SOURCE" == http*://* || "$REPO_SOURCE" == git@* ]]; then
  if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" fetch --quiet
    git -C "$APP_DIR" checkout --quiet apex/unified-field-integration
    git -C "$APP_DIR" pull --quiet
  else
    git clone --quiet --branch apex/unified-field-integration "$REPO_SOURCE" "$APP_DIR"
  fi
else
  rsync -a --delete --exclude 'runtime/' --exclude '.git/' "${REPO_SOURCE%/}/" "$APP_DIR/"
fi
chown -R "$APEX_USER:$APEX_USER" "$APEX_HOME"

# ---- 4. Python environment --------------------------------------------------
log "Creating venv and installing dependencies (cryptography only - matches CI)..."
sudo -u "$APEX_USER" python3.12 -m venv "$APP_DIR/.venv"
sudo -u "$APEX_USER" "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$APEX_USER" "$APP_DIR/.venv/bin/pip" install --quiet cryptography pytest

# runtime/ holds real local state (SQLite journal, inbox, logs) - never shipped from the
# repo, created fresh here, owned by the unprivileged user only.
sudo -u "$APEX_USER" mkdir -p "$APP_DIR/runtime/inbox" "$APP_DIR/runtime/rules" "$APP_DIR/runtime/logs"
chmod 700 "$APP_DIR/runtime"

# ---- 5. Firewall: 22 and the health port only, deny everything else --------
log "Configuring ufw: allow 22, allow ${HEALTH_PORT}, deny all else..."
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow "${HEALTH_PORT}/tcp"
ufw --force enable

# ---- 6. fail2ban (SSH jail, default config - no custom rules invented) -----
log "Enabling fail2ban (default jail, SSH)..."
systemctl enable --now fail2ban

# ---- 7. Integrity gate: A-17 MUST pass before this deploy is considered good
log "Running the A-17 adversarial evaluation suite as an integrity gate..."
if ! sudo -u "$APEX_USER" env PYTHONPATH="$APP_DIR/core" PYTHONDONTWRITEBYTECODE=1 \
     "$APP_DIR/.venv/bin/python3" -B -m unittest tests.test_adversarial_evaluation -v 2> "$APP_DIR/runtime/logs/a17_startup_$(date +%Y%m%dT%H%M%S).log"; then
  log "FATAL: A-17 adversarial evaluation suite did not fully pass. See the log above."
  log "Deployment stops here - an unverified kernel is not installed as a running service."
  exit 1
fi
log "A-17 suite: all probes PASS."

# ---- 8. Full verification (pytest, as requested) ----------------------------
log "Running the full test suite (pytest) as final verification..."
if ! sudo -u "$APEX_USER" env PYTHONPATH="$APP_DIR/core:$APP_DIR/tests" PYTHONDONTWRITEBYTECODE=1 \
     "$APP_DIR/.venv/bin/python3" -m pytest "$APP_DIR/tests" -q; then
  log "FATAL: test suite did not pass. Deployment stops here."
  exit 1
fi
log "Full suite: PASS."

# ---- 9. systemd unit + timer (oneshot --once per firing, NOT an infinite loop,
#         NOT an unattended-real-action daemon - agents_runner.py --once only proposes) --
log "Installing systemd unit and timer (--once per firing, propose-only)..."
cp "$APP_DIR/deploy/production/apex_kernel.service" /etc/systemd/system/apex_kernel.service
cp "$APP_DIR/deploy/production/apex_kernel.timer" /etc/systemd/system/apex_kernel.timer
systemctl daemon-reload
systemctl enable --now apex_kernel.timer

log "Done. apex_kernel.timer is active; each firing runs 'agents_runner.py --once' as the"
log "unprivileged '$APEX_USER' user. Nothing auto-executes an approved action - that still"
log "requires the owner's own click in the approval console, unchanged from this codebase's"
log "existing ActionGateway/ApprovalBook design."
log "Check status with: systemctl status apex_kernel.timer ; journalctl -u apex_kernel.service"
