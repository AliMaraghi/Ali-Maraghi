#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose config -q
docker compose ps
curl --fail --silent http://127.0.0.1:8080/healthz
printf '\n\nBrowser (via Tailscale Serve): open server tailnet HTTPS address\n'
