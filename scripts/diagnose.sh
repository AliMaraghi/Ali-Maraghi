#!/usr/bin/env bash
# Read-only health report for APEX. Changes nothing. Run on the server; send the output file to Claude.
cd "$(dirname "$0")/.." || exit 1
echo "== APEX diagnose $(date -u +%FT%TZ) =="; echo "-- code version"; git log --oneline -1 2>&1
echo; echo "-- memory and disk"; free -m 2>&1 | head -3; df -h . 2>&1 | tail -1
echo; echo "-- services"
for u in apex-voice apex-ui apex-console apex-worker apex-agents ollama cloudflared; do
  printf '%-14s system=%s user=%s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null)" "$(systemctl --user is-active "$u" 2>/dev/null)"
done
echo; echo "-- timers"; systemctl --user list-timers --no-pager 2>&1 | head -12; systemctl list-timers 'apex*' --no-pager 2>&1 | head -8
for u in apex-console apex-worker apex-agents apex-voice; do
  echo; echo "-- last 50 log lines: $u"
  (journalctl -u "$u" -n 50 --no-pager 2>/dev/null; journalctl --user -u "$u" -n 50 --no-pager 2>/dev/null) | tail -50 \
    | sed -E 's/(key|token|secret|password|authorization)([=: ]+)[^ ]+/\1\2[hidden]/Ig'
done
echo; echo "-- database"
python3 - <<'PY'
import sqlite3, os
p = "runtime/kernel.sqlite3"
for s in ("", "-wal", "-shm"):
    print(p + s, os.path.getsize(p + s) if os.path.exists(p + s) else "absent")
try:
    db = sqlite3.connect("file:" + p + "?mode=ro", uri=True, timeout=5)
    print("integrity:", db.execute("PRAGMA integrity_check").fetchone()[0], "| journal:", db.execute("PRAGMA journal_mode").fetchone()[0])
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        print(f"  {name}: {db.execute(f'SELECT COUNT(*) FROM \"{name}\"').fetchone()[0]} rows")
    print("google sync rows:", db.execute("SELECT COUNT(*) FROM google_private_sync").fetchone()[0])
except Exception as e:
    print("DATABASE ERROR:", type(e).__name__, e)
PY
echo; echo "-- recovery folder"; ls -la runtime/recovery 2>&1 | head; echo "== end =="
