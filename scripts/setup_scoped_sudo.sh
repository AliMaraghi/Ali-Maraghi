#!/usr/bin/env bash
# Install a NARROW sudo policy for apexdev: restart/status of the three APEX units, nothing else.   Run once:  sudo bash scripts/setup_scoped_sudo.sh
# Why these exact lines (differences from the request are deliberate):
#  * unit names: there is no "apex-core" unit; the real units are apex-console, apex-worker and apex-legal (all run as apexdev, not root, so restarting them gives no extra privilege).
#  * `status` is allowed only as `systemctl --no-pager status <unit>` with the NOEXEC tag: an unrestricted pager (less) run through sudo can spawn a root shell.
#  * docker is NOT included: `docker compose -f /home/apexdev/apex-work/compose.yaml ...` reads a file apexdev can edit, so allowing it would let apexdev start any container as root
#    (root-equivalent). A docker rule is only least-privilege if the compose file is root-owned and read-only to apexdev; do that deliberately and separately if you really need it.
# Revert at any time:  sudo rm /etc/sudoers.d/apex_limits
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[ "$(id -u)" -eq 0 ] || { echo "STOPPED: run with sudo" >&2; exit 1; }
id apexdev >/dev/null 2>&1 || { echo "STOPPED: user apexdev missing" >&2; exit 1; }
SYSTEMCTL="$(command -v systemctl)"
[ "$SYSTEMCTL" = "/usr/bin/systemctl" ] || { echo "STOPPED: unexpected systemctl path $SYSTEMCTL" >&2; exit 1; }
TARGET=/etc/sudoers.d/apex_limits
TMP="$(mktemp /etc/sudoers.d/.apex_limits.XXXXXX)"      # names containing a dot are ignored by sudo until renamed
trap 'rm -f -- "${TMP:?}"' EXIT
cat > "$TMP" <<'RULES'
# Managed by scripts/setup_scoped_sudo.sh. Exact command lines only; no wildcards, no shells, no docker.
Cmnd_Alias APEX_UNITS = \
    /usr/bin/systemctl restart apex-console.service, \
    /usr/bin/systemctl restart apex-worker.service, \
    /usr/bin/systemctl restart apex-legal.service, \
    /usr/bin/systemctl --no-pager status apex-console.service, \
    /usr/bin/systemctl --no-pager status apex-worker.service, \
    /usr/bin/systemctl --no-pager status apex-legal.service
apexdev ALL=(root) NOPASSWD: NOEXEC: APEX_UNITS
RULES
visudo -cf "$TMP"
install -m 0440 -o root -g root "$TMP" "$TARGET"
visudo -c >/dev/null
echo "Installed $TARGET. apexdev may now run, without a password, exactly:"
sudo -l -U apexdev | sed -n '/APEX_UNITS\|systemctl/p'
