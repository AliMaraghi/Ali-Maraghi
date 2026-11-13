#!/usr/bin/env bash
# APEX owner handoff: the only privileged step. Run as root:  sudo bash scripts/owner_handoff.sh [prepare|activate]
#   prepare  (default) binds Cloudflare Access, writes /etc/apex/approvals-runtime.json, installs the legal-pages service, enables linger.
#   services installs apex-bridge.service and apex-agents.service from the repo, restarts apex-console to load the /bridge page, and checks them.
#   activate runs the REVIEWED production installer (it runs the full test suite as its own gate), then optionally provisions Google/Meta.
# It never touches DNS, tunnel routes, other services or existing files that differ (it stops instead of overwriting).
set -Eeuo pipefail
umask 022   # the reviewed installer relies on the default 022 so apexdev can read root-owned public config
export PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8
REPO=/home/apexdev/apex-work
SVC=apexdev
PHASE="${1:-prepare}"
say() { printf '\n== %s\n' "$*"; }
die() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run with sudo"
[ "$(cat /proc/1/comm)" = "systemd" ] || die "PID 1 is not systemd; run on the real host"
id "$SVC" >/dev/null 2>&1 || die "user $SVC missing"
[ "$(readlink -f "$REPO")" = "$REPO" ] || die "repository path is not canonical"

if [ "$PHASE" = "prepare" ]; then
  say "1/6 Validate the reviewed bundle (no changes)"
  /usr/bin/python3 -I -B "$REPO/deploy/production/install.py" | grep -q BUNDLE_CHECKED_NOT_DEPLOYED || die "bundle validation failed"

  say "2/6 Read the Cloudflare Access team and application AUD from the live console redirect (public identifiers)"
  eval "$(/usr/bin/python3 -I - <<'PY'
import base64, json, re, subprocess
out = subprocess.run(["curl", "-sS", "-m", "15", "-o", "/dev/null", "-D", "-", "https://console.apexcorelab.uk/"],
                     capture_output=True, text=True).stdout
try:
    loc = re.search(r"(?im)^location:\s*(\S+)", out).group(1)
    team = re.match(r"https://([a-z0-9-]{1,63})\.cloudflareaccess\.com/", loc).group(1)
    seg = re.search(r"[?&]meta=([A-Za-z0-9_.-]+)", loc).group(1).split(".")[1]
    aud = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))["aud"]
    assert re.fullmatch(r"[a-f0-9]{64}", aud)
    print(f"TEAM={team}\nAUD={aud}")
except Exception:
    print("TEAM=\nAUD=")
PY
)"
  [ -n "${TEAM:-}" ] && [ -n "${AUD:-}" ] || die "could not read team/AUD from https://console.apexcorelab.uk/ (is the tunnel up?)"
  echo "   team: $TEAM   aud: $AUD"

  say "3/6 Owner e-mail (the single identity allowed through Cloudflare Access)"
  OWNER="${OWNER_EMAIL:-}"
  if [ -z "$OWNER" ]; then read -r -p "   Access owner e-mail: " OWNER; fi
  printf '%s' "$OWNER" | grep -Eq '^[^[:space:]@,<>]+@[^[:space:]@,<>]+\.[^[:space:]@,<>]+$' || die "invalid e-mail"

  say "4/6 /etc/apex: Access snapshot (reviewed installer) and approvals configuration"
  install -d -m 0755 -o root -g root /etc/apex
  /usr/bin/python3 -I -B "$REPO/deploy/production/install.py" --bind-access --team "$TEAM" --aud "$AUD" --owner "$OWNER"
  OWNER="$OWNER" /usr/bin/python3 -I - <<'PY'
import json, os, pwd, secrets, tempfile
target, owner = "/etc/apex/approvals-runtime.json", os.environ["OWNER"]
svc = pwd.getpwnam("apexdev")
if os.path.exists(target):
    with open(target) as f:
        existing = json.load(f)
    if existing.get("owner") != owner or len(existing.get("approval_secret", "")) < 32:
        raise SystemExit("STOPPED: existing approvals-runtime.json differs; not overwriting")
    print("   approvals-runtime.json already present and consistent: kept")
else:
    fd, tmp = tempfile.mkstemp(dir="/etc/apex", prefix=".approvals-")
    with os.fdopen(fd, "w") as f:
        json.dump({"owner": owner, "approval_secret": secrets.token_urlsafe(48)}, f)
    os.fchown(os.open(tmp, os.O_RDONLY), svc.pw_uid, svc.pw_gid)
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    print("   wrote /etc/apex/approvals-runtime.json (apexdev:apexdev 0600; random secret, not displayed)")
PY
  ls -l /etc/apex

  say "5/6 Legal pages as a managed service (replaces the temporary session-run server)"
  UNIT_SRC="$REPO/deploy/legal/apex-legal.service"; UNIT_DST=/etc/systemd/system/apex-legal.service
  systemd-analyze verify "$UNIT_SRC"
  if [ -e "$UNIT_DST" ] && ! cmp -s "$UNIT_SRC" "$UNIT_DST"; then die "$UNIT_DST exists and differs; not overwriting"; fi
  for pid in $(pgrep -u "$SVC" -f '^python3 -I deploy/legal/serve_legal.py --directory' || true); do kill "$pid"; done
  sleep 1
  install -m 0644 -o root -g root "$UNIT_SRC" "$UNIT_DST"
  systemctl daemon-reload
  systemctl enable --now apex-legal.service
  sleep 2
  systemctl is-active --quiet apex-legal.service || die "apex-legal.service did not start (journalctl -u apex-legal.service)"
  curl -fsS -m 5 -o /dev/null -w '   local /privacy: HTTP %{http_code}\n' http://127.0.0.1:8787/privacy
  curl -fsS -m 5 -o /dev/null -w '   local /terms:   HTTP %{http_code}\n' http://127.0.0.1:8787/terms

  say "6/6 Enable linger for $SVC"
  loginctl enable-linger "$SVC"
  loginctl show-user "$SVC" -p Linger

  say "DONE (prepare). Nothing else was changed. Next: tell Claude APPROVED so the pre-activation check runs; then run:  sudo bash $REPO/scripts/owner_handoff.sh activate"

elif [ "$PHASE" = "activate" ]; then
  [ -f /etc/apex/access-origin.json ] || die "run the prepare phase first"
  say "1/3 Reviewed production installer (installs python3-waitress via apt, runs the test suite as its gate, backs up the journal, installs and starts apex-console and apex-worker)"
  /usr/bin/python3 -I -B "$REPO/deploy/production/install.py" --apply --install-dependencies
  say "2/3 Optional connection secrets (typed hidden; each script asks you to type REVIEWED to attest the privacy review)"
  for item in google meta; do
    read -r -p "   Configure $item now? [y/N] " ans
    if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then /usr/bin/python3 -I -B "$REPO/deploy/production/provision_$item.py"; fi
  done
  say "3/3 Local checks"
  systemctl is-active apex-console.service apex-worker.service apex-legal.service
  curl -sS -m 5 -o /dev/null -w '   console without token (expect 401): HTTP %{http_code}\n' http://127.0.0.1:8765/console || true
  say "DONE (activate). Sign in once through your browser: https://console.apexcorelab.uk/connections/google  and  /connections/meta"
elif [ "$PHASE" = "services" ]; then
  [ -f /etc/apex/access-origin.json ] || die "run the prepare phase first"
  say "1/3 Install the two new units (apex-bridge: loopback endpoint for the laptop agent; apex-agents: propose-only agents every 5 minutes)"
  for unit in apex-bridge apex-agents; do
    src="$REPO/deploy/production/$unit.service"; dst="/etc/systemd/system/$unit.service"
    systemd-analyze verify "$src"
    if [ -e "$dst" ] && ! cmp -s "$src" "$dst"; then die "$dst exists and differs; not overwriting"; fi
    install -m 0644 -o root -g root "$src" "$dst"
  done
  systemctl daemon-reload
  say "2/3 Restart the console so the /bridge page is loaded, then start the new services"
  systemctl restart apex-console.service
  systemctl enable --now apex-bridge.service apex-agents.service
  sleep 3
  say "3/3 Checks"
  systemctl is-active apex-console.service apex-worker.service apex-bridge.service apex-agents.service apex-legal.service
  curl -fsS -m 5 http://127.0.0.1:8770/bridge/health; echo
  curl -sS -m 5 -o /dev/null -w '   console without token (expect 401): HTTP %{http_code}\n' http://127.0.0.1:8765/console || true
  say "DONE (services). Remaining owner steps: (1) Cloudflare route apexcorelab.uk/bridge -> HTTP 127.0.0.1:8770, (2) create the bridge key at https://console.apexcorelab.uk/bridge, (3) run laptop_agent.py"
else
  die "usage: sudo bash $0 [prepare|activate|services]"
fi
