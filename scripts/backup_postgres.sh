#!/usr/bin/env bash
# Example local backup; production MUST encrypt and copy off-server.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/apex-$(date +%Y%m%d-%H%M%S).sql"
docker compose exec -T postgres pg_dump -U apex apex > "$out"
chmod 600 "$out"
echo "Local database dump: $out (not encrypted; move to secure encrypted storage)"
