#!/usr/bin/env python3
"""Interactive, one-time setup for Open Banking credentials - writes
/etc/apex/banking-runtime.json (apexdev, chmod 600), the file core/apex/banking_web.py and
console_server.py actually read. NOT /etc/apex/truelayer.json: that path matches no code in
this repo, so a file written there would silently do nothing. The script is named
setup_truelayer.py because that's the aggregator currently being set up, but what it produces
is the generic banking-runtime.json shape banking_connect.py expects - nothing here is
TrueLayer-specific beyond the host/path defaults below, which you should confirm against
TrueLayer's own current developer docs before trusting them (this script does not call
TrueLayer or validate them against a live endpoint).

Run this ON THE SERVER, as the apexdev user (or via sudo -u apexdev), never over a connection
you don't trust - the client secret is typed at a hidden prompt and never echoed, logged or
written anywhere except the one output file.

  python3 scripts/setup_truelayer.py
"""
from __future__ import annotations

import getpass
import json
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

CONFIG_PATH = Path("/etc/apex/banking-runtime.json")
CONSOLE_ORIGIN = "https://console.apexcorelab.uk"

# TrueLayer's documented sandbox/live hosts as of this writing - CONFIRM against
# https://docs.truelayer.com before trusting; this script does not verify them live.
DEFAULTS = {
    "host": "auth.truelayer-sandbox.com",
    "authorize_path": "/",
    "token_path": "https://auth.truelayer-sandbox.com/connect/token",
    "accounts_path": "https://api.truelayer-sandbox.com/data/v1/accounts",
    "transactions_path": "https://api.truelayer-sandbox.com/data/v1/accounts/{account_id}/transactions",
    "provider_id": "truelayer-sandbox",
}


def prompt(label, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default or ""


def main():
    if os.geteuid() == 0:
        sys.exit("Run this as the apexdev user, not root - the output file is owned by apexdev.")

    print(__doc__.split("\n\n")[1])
    print()
    owner = prompt("Owner email (must exactly match the Cloudflare Access identity)")
    if not re.fullmatch(r"[^\s@,<>]+@[^\s@,<>]+\.[^\s@,<>]+", owner):
        sys.exit("A single valid email address is required.")

    client_id = prompt("TrueLayer Client ID")
    client_secret = getpass.getpass("TrueLayer Client Secret (hidden, not echoed): ")
    if not client_id or not client_secret:
        sys.exit("Client ID and Client Secret are both required.")

    print("\nPress Enter to accept each default, or type a different value "
          "(only change these if you know your real TrueLayer app's exact endpoints):")
    host = prompt("Authorization host", DEFAULTS["host"])
    authorize_path = prompt("Authorization path", DEFAULTS["authorize_path"])
    token_path = prompt("Token endpoint (full URL)", DEFAULTS["token_path"])
    accounts_path = prompt("Accounts endpoint (full URL)", DEFAULTS["accounts_path"])
    transactions_path = prompt("Transactions endpoint (full URL, optional)", DEFAULTS["transactions_path"])
    provider_id = prompt("Provider id (a short label, not sent to TrueLayer)", DEFAULTS["provider_id"])

    from cryptography.fernet import Fernet
    encryption_key = Fernet.generate_key().decode()

    config = {
        "owner": owner,
        "encryption_key": encryption_key,
        "scopes": ["info", "accounts", "transactions", "offline_access"],
        "config": {
            "host": host,
            "authorize_path": authorize_path,
            "token_path": token_path,
            "accounts_path": accounts_path,
            "transactions_path": transactions_path,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": CONSOLE_ORIGIN + "/auth/banking/callback",
            "provider_id": provider_id,
        },
    }

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
    finally:
        os.chmod(CONFIG_PATH, 0o600)

    mode = stat.S_IMODE(CONFIG_PATH.stat().st_mode)
    print(f"\nWrote {CONFIG_PATH} (mode {oct(mode)}).")
    print("Restart apex-console.service to pick it up:")
    print("  sudo systemctl restart apex-console.service")
    print("\nThis does NOT connect to your bank yet. It only makes "
          f"{CONSOLE_ORIGIN}/connections/banking reachable (behind the real Cloudflare Access "
          "login) - you still complete the real OAuth consent yourself, in your own browser, "
          "logged in as the owner.")


if __name__ == "__main__":
    main()
