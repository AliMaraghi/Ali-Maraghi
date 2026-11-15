# Scheduler 7-day soak runbook (owner-run, real machine)

This is the REAL-time counterpart to `tests/test_scheduler.py`'s
`SevenDaySoakTests` (accelerated clock, proven in under 2 seconds of wall
time). An accelerated test proves the LOGIC is correct; it does not prove the
process survives a real week on the real machine (memory growth, disk growth,
log rotation, an actual OS reboot, a real power cut). Only the owner, on the
personal machine, with real elapsed time, can prove that. This file is the
exact procedure - it is not run by any session working in this repository.

## Prerequisites

- A dedicated, disposable `runtime/` directory for this soak - do not point it
  at the real production ledger.
- Python 3.11+, this repo checked out, no other change needed.

## 1. Write a tiny harness script (owner does this once)

```python
#!/usr/bin/env python3
"""scripts/soak_scheduler.py - NOT checked in by this session; the owner creates
this file locally for the soak only, pointed at a disposable runtime dir."""
import sys, time
from pathlib import Path
sys.path.insert(0, "core")
from apex.kernel.memory import Ledger
from apex.kernel.scheduler import ClockSource, JobQueue, SchedulerLoop

root = Path("runtime_soak")   # disposable - never the real runtime/
ledger = Ledger(root)
queue = JobQueue(ledger)

def heartbeat_action(ctx, payload):
    print(f"heartbeat {payload['window']} at {time.time()}", flush=True)

source = ClockSource("heartbeat", 3600, "heartbeat_action",
                      payload_fn=lambda now: {"window": int(now // 3600)})
loop = SchedulerLoop(ledger, queue, {"heartbeat_action": heartbeat_action}, [source])
loop.recover_on_start()
print("Soak started. Leave this running for 7 real days.", flush=True)
while True:
    loop.tick()
    time.sleep(60)
```

## 2. Run it under a real process supervisor, not just a terminal

```bash
nohup python3 -B scripts/soak_scheduler.py > runtime_soak_log.txt 2>&1 &
echo $! > runtime_soak.pid
```

If the owner reboots the machine during the 7 days, re-run the same command -
`loop.recover_on_start()` requeues anything left `RUNNING` (there should be
none here, since `heartbeat_action` never blocks), and `ClockSource`'s
no-catch-up policy means only the current hour fires after the gap, not a
flood of missed hours - note any gap in the log as an expected consequence of
that documented policy, not a bug.

## 3. What to check after 7 real days

```bash
python3 -B -c "
import sys; sys.path.insert(0, 'core')
from apex.kernel.memory import Ledger
from apex.kernel.scheduler import JobQueue
ledger = Ledger('runtime_soak')
queue = JobQueue(ledger)
snap = queue.snapshot()
print('total jobs:', len(snap))
print('states:', {s['state'] for s in snap})
print('ledger length:', ledger.verify())
"
```

Pass criteria (mirroring the accelerated test's own gate):
- `total jobs` is close to 168 (24 * 7) - allow for any real reboot gaps,
  which should be individually explainable from the log, not silent.
- `states` contains only `DONE` (no stray `RUNNING`/`FAILED` left over).
- `ledger.verify()` returns cleanly (no `ValueError`) - the audit chain
  survived a real week of real writes, including through any real reboot.
- `runtime_soak_log.txt` shows one heartbeat line per hour, in order, with no
  duplicate window numbers - the same "zero lost, zero duplicate" property
  the accelerated test checks, now over real wall-clock time.

## 4. Afterward

Delete `runtime_soak/`, `runtime_soak_log.txt`, `runtime_soak.pid`, and
`scripts/soak_scheduler.py` - none of this is meant to be a permanent fixture;
it is a one-time real-time verification of what the accelerated test already
proved logically.
