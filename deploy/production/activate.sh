#!/bin/sh
# Root-run production activation using the existing reviewed installer unchanged.
# Usage (in a root shell, NOT inside Claude Code):
#   sh /home/apexdev/apex-work/deploy/production/activate.sh 'owner@example.com'
# Safe to repeat: Access binding refuses a different identity, identical units are
# kept, the database is retained and backed up on every run. Writes a non-secret
# receipt to /tmp/apex-install-receipt.txt (no email, keys or tokens).
set -u
INSTALL=/home/apexdev/apex-work/deploy/production/install.py
TEAM=wispy-limit-fad4
AUD=7e80f52337f480b9f5e877248ffda1e4c71d0956eda62999ba6ad2622a3f6a4a
RECEIPT=/tmp/apex-install-receipt.txt
[ "$(id -u)" = 0 ] || { echo 'Run as root'; exit 1; }
[ $# -eq 1 ] || { echo "Usage: sh $0 'owner@example.com'"; exit 1; }
case "$1" in *@*.*) ;; *) echo 'Owner email required'; exit 1;; esac
umask 022
{
  echo "date: $(date -u +%FT%TZ)"
  echo "boot_id: $(cat /proc/sys/kernel/random/boot_id)"
  python3 -I -B "$INSTALL" --bind-access --team "$TEAM" --aud "$AUD" --owner "$1"
  rc=$?; echo "EXIT1=$rc"
  if [ "$rc" = 0 ]; then
    python3 -I -B "$INSTALL" --apply --install-dependencies
    echo "EXIT2=$?"
  fi
  systemctl is-active apex-console.service apex-worker.service apex-access-jwks.timer
  systemctl is-enabled apex-console.service apex-worker.service apex-access-jwks.timer
} 2>&1 | tee "$RECEIPT"
chmod 0644 "$RECEIPT"
