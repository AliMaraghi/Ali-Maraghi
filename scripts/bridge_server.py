#!/usr/bin/env python3
"""Run the laptop-bridge endpoint on 127.0.0.1:8770 (the Cloudflare route apexcorelab.uk/bridge points here). Packaged as deploy/production/apex-bridge.service."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from apex.bridge_server import make_server      # noqa: E402

if __name__ == "__main__":
    server = make_server(ROOT, int(sys.argv[1]) if len(sys.argv) > 1 else 8770)
    print("APEX bridge endpoint on 127.0.0.1:%d (authenticated, loopback only)" % server.server_address[1], flush=True)
    server.serve_forever()
