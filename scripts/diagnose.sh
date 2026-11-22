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
    | sed -E 's/(key|token|secret|password|authorization)([=: ]+)[^ ]+/\1\2[hidden]/Ig' \
    | cut -c1-320 | awk '{k=$0; sub(/^[A-Z][a-z]+ +[0-9]+ [0-9:]+ /,"",k); gsub(/[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z/,"",k); if(k==prev){n++} else {if(n>0)print "   (previous line repeated " n " more times)"; print; n=0; prev=k}} END{if(n>0)print "   (previous line repeated " n " more times)"}'
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
echo; echo "-- which code each service loaded (process start vs latest commit)"
echo "latest commit: $(git log -1 --format='%cI %h' 2>&1)"
for u in apex-voice apex-ui apex-console apex-worker apex-agents; do
  pid=$(systemctl show -p MainPID --value "$u" 2>/dev/null)
  printf '%-14s pid=%s started=%s\n' "$u" "$pid" "$( [ -n "$pid" ] && [ "$pid" != 0 ] && ps -o lstart= -p "$pid" 2>/dev/null )"
done
echo; echo "-- Gmail connector audit trail (ledger: arm / disarm / run events; no mail content)"
python3 - <<'PY'
import sqlite3, json, time
try:
    db = sqlite3.connect("file:runtime/kernel.sqlite3?mode=ro", uri=True, timeout=5)
    rows = db.execute("SELECT seq, event_key, payload FROM events WHERE event_key LIKE 'connector-%' ORDER BY seq DESC LIMIT 14").fetchall()
    for seq, key, payload in reversed(rows):
        p = json.loads(payload)
        stamp = next((int(x) for x in key.split('-') if x.isdigit() and len(x) >= 10), None)
        when = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(stamp)) if stamp else '?'
        print(f"  seq {seq} | {key.rsplit('-', 1)[0] if 'run' in key else key} | {when} | "
              + ", ".join(f"{k}={p[k]}" for k in ('phase', 'state', 'error_type', 'consecutive_failures', 'disabled', 'reason') if k in p))
    print("schedule now:", db.execute("SELECT enabled, remaining, issued, failures, pending, next_due FROM connector_schedules WHERE connector='gmail'").fetchone())
    print("-- mission schedules (worker)")
    for sid, enabled, remaining, issued in db.execute("SELECT id, enabled, remaining, issued FROM mission_schedules"):
        print(f"  {sid}: enabled={enabled} remaining={remaining} issued={issued}")
    print("-- pending approvals by proposer (same table the console queue shows)")
    for proposer, n in db.execute("SELECT proposer, COUNT(*) FROM proposals WHERE state='PENDING' GROUP BY proposer"):
        print(f"  {proposer}: {n}")
except Exception as e:
    print("AUDIT QUERY ERROR:", type(e).__name__, e)
PY
echo; echo "-- recovery folder"; ls -la runtime/recovery 2>&1 | head; echo "== end =="
