# Security findings — 2026-11-10

Reference-only defects reproduced in `review_kit_audit.json`:

| Finding | Evidence | Disposition |
|---|---|---|
| Worker runs with STOP_EXECUTION | run_one completes a synthetic job after kill | Reject reference worker/queue |
| Old attempt can acknowledge reclaimed lease | same worker name reacquires; no attempt token in finish | Require fenced attempt identity before any worker import |
| Mutation commits without audit | injected event failure leaves queued task without event | Retain existing atomic workflow transaction |
| NaN cost permitted | both numeric comparisons false, gateway allows request | Retain strict integer zero-budget policy |
| Fractional coverage accepted | 1.5 observed/inspected, 0.5 selected reports full coverage | Adapt with strict integers and snapshot membership tests |

These are synthetic memory-only reproductions, not incidents on production.
All five remain in the immutable reference; none was imported into the runtime.
`scripts/audit_review_kit.py --probe-reference` rechecks hashes before importing
the reference solely for the isolated probes.

Current residual risks: single-user unencrypted SQLite; owner can rewrite an
entire hash chain; no authenticated external authority; no enforced worker/global
stop; parse-only URLs are not SSRF-safe fetches; caller-declared public/synthetic
classification is not DLP; reported source independence is not proven. Existing
web routes are not a secure private command plane and were not started.

OWP inputs are data only: no shell, SQL, URL fetch or model invocation is derived
from them. The adaptation caps axes/sources/probes and file bytes, rejects unknown
fields, expired requests, private/IP endpoints, non-integer costs and source-ID
collisions. Coverage rejects tampering, paths outside workspace, symlinks, stale
snapshots and impossible membership. Tests do not establish production security.
