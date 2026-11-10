# Recovery and rollback

Observed: `scripts/smoke_local_recovery.py` creates one synthetic decision in an
isolated workspace temp journal, uses SQLite's backup API to a second isolated
journal, closes/reopens read-only, verifies the chain and exact record equality.
Result: `reports/validation/epoch_local_restore.json`. The temp journals are removed.
Its single timing is not a production MTTR/SLO measurement.

Production DB restore, encrypted/offsite backups, restore authorization, retention,
credential recovery and service continuity: NOT RUN / BLOCKED. No live journal or
production database is read by the smoke script. Do not copy a running SQLite main
file without handling transactions/WAL; use the tested backup API in a separately
reviewed, authorized maintenance procedure.

For a development regression, inspect local commits/diff and use a reviewed revert
of the offending increment. Do not reset shared history, erase a journal or
overwrite user changes. `bcde451` is the pre-override code baseline; `0cb89f8` is
the tested durable workflow checkpoint. Subsequent OWP integration has no database
migration. Reverting code can change input fingerprints: use an explicit new task
ID for reevaluation; historical readonly reports remain historical, not current.

If chain verification fails, stop writes and preserve evidence in the authorized
workspace. Do not silently reconstruct or delete events. Request the narrow
maintenance authority required before touching any non-development store.
