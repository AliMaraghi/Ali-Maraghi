#!/usr/bin/env python3
"""Read-only status of the agents and the laptop bridge (no sudo, no network).  python3 scripts/agents_status.py"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from apex.kernel.memory import Ledger      # noqa: E402

with Ledger.read_only(ROOT) as ledger:
    runs = [(r["key"], r["payload"]) for dom in ("opportunity", "personal", "studio") for r in ledger.records(dom) if r["payload"].get("event") == "agent_run"]
    runs.sort(key=lambda item: int(item[0].rsplit(".", 1)[-1]))
    print(f"agent runs recorded: {len(runs)}")
    for key, payload in runs[-9:]:
        when = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(int(key.rsplit('.', 1)[-1])))
        print(f"  {when}  {payload['agent']:<5} {payload['status']:<6} confidence={payload.get('confidence')} error={payload.get('error')}")
    try:
        tables = {n for (n,) in ledger.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "bridge_meta" in tables:
            poll = ledger.db.execute("SELECT v FROM bridge_meta WHERE k='last_poll'").fetchone()
            print("laptop agent last polled:", "never" if not poll else f"{int(time.time() - poll[0])} s ago")
            print("bridge tasks:", dict(ledger.db.execute("SELECT state, COUNT(*) FROM bridge_tasks GROUP BY state")) or "none")
    except Exception as exc:
        print("bridge status unavailable:", type(exc).__name__)
