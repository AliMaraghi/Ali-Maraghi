# Local development operations

Run from `/home/apexdev/apex-work`. Read NEXT_ACTION.md and `git status` first.
No daemon, production access, Docker, paid API or external write is authorized.

```
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py
python3 -B scripts/traceability.py
python3 -B scripts/export_requirement_ledger.py
python3 -B scripts/audit_review_kit.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmark_kernel.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/smoke_local_recovery.py
PYTHONPATH=core python3 -B -m apex.kernel.cli owp-plan examples/owp_search_synthetic.json
PYTHONPATH=core python3 -B -m apex.kernel.cli owp-coverage examples/owp_coverage_synthetic.json
```

The OWP examples expire on 20 November. After expiry they must fail; prepare a new
dated request/snapshot after review, never silently refresh evidence timestamps.
Source candidates are synthetic example.org entries, not fetched datasets.

The workflow CLI accepts a task/case packet. Use a new task ID for changed inputs
or code versions; exact retry returns the original stored report. Report/history
readers open SQLite in read-only mode and do not create a store. Replay explicitly
does not recheck source freshness. Runtime state is ignored under `runtime/`.

Statuses: an unexecuted probe is preparation; source eligibility is not truth;
REVIEW_COMPLETED is not an empirical experiment; no workflow report promotes code.
Invalid input returns exit 2 with a redacted error type. Full source/exception
content must not be copied into public logs. Sensitive data is unsupported.

`--kill-state STOP_EXECUTION` prevents workflow/OWP planning in that invocation.
This is not a durable global kill switch. No background task survives this chat.
Do not run legacy Docker/service/backup/monitor scripts listed in AGENTS.md.

## Durable jobs increment (supersedes earlier absence of a queue)

Use jobs-submit with a task/case packet, jobs-run-one with a worker ID, and
jobs-status for a readonly view. jobs-control --state STOP_EXECUTION commits local
stop; jobs-control --state RUNNING is an explicit trusted local-operator resume.
No network/model handler can be queued. Every mutation couples its audit event
transactionally. Handler result and job completion commit together. Lease attempts
are fenced by tokens; max3 attempts and bounded backoff; exhausted crashes dead-letter.
Only one iteration runs per invocation; no background process or cron was installed.

Status COMPLETE is processing status; consult workflow_status and its report for
blocked evidence. STOP is graceful: it waits behind an active write transaction,
and lock timeout must be reported as failure. It is not production global stop.
Current caps:100 active/1000 retained jobs,262144-byte payload,15–300-second lease.
Source script is separately invoked, bounded and live-blocked; PUBLIC_SOURCE_ADAPTER.md.
