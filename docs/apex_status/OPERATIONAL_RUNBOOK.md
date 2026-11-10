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
