# Operational checkpoint — 2026-11-10

Branch apex/four-layer-owp-integration; entry HEAD9f2a920. Latest verified code
commit is in CHECKPOINT.json and local Git history. The uploaded ZIP remains
untracked/unchanged. Original documents and all four-plane requirements retained.
Previous report preserved as NIGHT_SHIFT_REPORT_20261110_epoch.md.

## What now runs

The existing evidence workflow now has a persistent local queue: submit a typed
Task/Case, claim one attempt, enforce durable stop, run the fixed workflow, commit
its result and the matching job/audit atomically, then read the historical report.
No arbitrary handlers or network tools are available to queued input. No daemon,
production deployment, mobile endpoint, paid service or account integration ran.

Three missing operational controls were implemented in existing kernel modules:
STOP_EXECUTION enforcement at dispatch, attempt-token lease fencing (including
same-worker reuse), and transactional job/workflow/audit completion. Existing strict
finite integer cost and exact snapshot-count checks were preserved and retested.
The immutable reference still reproduces five defects; it remains excluded.

New code: kernel/jobs.py; nested savepoints in kernel/memory.py; four jobs-* CLI
commands. Additive job_meta(v1)/jobs tables; existing event schema/data retained
with new job event kind. Actual dev journal backed up before initialization under
ignored work/pre-jobs-20261110/. This is not a production backup or migration.

A separate explicit Contracts Finder source adapter implements fixed host/path,
validated DNS/IP-pinned TLS, redirect revalidation, response/time/request caps and
no retries. It is NOT wired to the worker. Two authorized public diagnostic calls
ran. The current endpoint returned more releases than the requested size5; the
client rejected it. No usable procurement packet or raw contact data was retained.
Current endpoint licence/request encoding verification remains pending. See
PUBLIC_SOURCE_ADAPTER.md for exact blocker and next integration requirements.

## Actual end-to-end execution

The real source failure receipt was made into a dated diagnostic evidence packet,
not synthetic market data. Eight separate CLI processes submitted/stopped/denied/
resumed/processed/read it. Result: job COMPLETE, workflow BLOCKED_PENDING_EVIDENCE;
unsupported upstream-fault inference was not accepted. Second worker run EMPTY;
readonly report linked the same durable result. Evidence:
reports/validation/operational_cli_e2e.json and the saved blocker case.

COMPLETE means job processing completed, never that evidence, demand or the full
mission was validated. The receipt timestamp is local capture-file mtime, not
upstream publication time. No market candidate or income was invented.

## Tests and comparative evidence

- Baseline rerun135 passed /2 optional web skips.
- Final full suite162 passed /2 optional FastAPI/httpx integration skips; no failures.
- Includes stop denial before handler, stale/foreign/expired lease denial, exact
  boundary expiry, retry cap/backoff/dead-letter recovery, two-process claims,
  actual os._exit during workflow completion, restart with rollback/no duplicate,
  submit/claim/control/completion audit failure and queue bounds.
- Source tests cover mixed DNS, redirect rebinding, peer pinning, hostname-verified
  TLS context, response limits/status/encoding, no implicit authority and killing
  a hung subprocess. Fixtures are synthetic; live compatibility remains BLOCKED.
- Frozen policy benchmark unchanged:24/24 kernel,13/24 weak rule,24/24 full checklist.
- Reference's five adverse cases still reproduce. These are regression cases,
  not independently defined holdouts or evidence of intelligence superiority.
- Original13 listed hashes match; trace178 groups/968 units retained. Canonical
  and historical six §5 sublayers,18 roles,0–18,appendices,A01–A09 remain.

TEST_EVIDENCE.csv records exact commands/logs/hashes. OPERATIONAL_INCREMENT_REVIEW.md
maps every defect to current control and test. CLI timings are observations of one
run, not a utility benchmark. Independent manual/model baseline utility, correction
minutes and real economic value are NOT MEASURED. No independent reviewer was
available; this was implementer self-review, not independent semantic acceptance.

## Remaining limits and next decision

Durable stop is local to this queue and graceful. In-flight transaction finishes
before concurrent stop commits; lock timeout is a failed stop, not success. Local
operator resume is not remote owner authentication. Source transport is separate;
queue stop does not cancel unrelated processes or credentials. Ledger remains
unencrypted/same-user trusted, with no protected external audit sink.

Next: verify current authoritative API parameter encoding and licence, preserve
strict caps, then accept one genuine bounded packet before market analysis. Obtain
an independent reviewer/fresh same-input baseline before value claims. Add staging
service lifecycle and authenticated private control only after separate security
and integration evidence. Film remains blocked by footage/rights/rendering/review.
All full manifesto acceptance remains open; nothing is reclassified as complete.

Additional paid API spendGBP0/USD0. Two public retrieval invocations; actual HTTP
hop counts were not retained on rejection (each bounded to2), so no exact hop count
is asserted. Hosting/subscription/human effort not separately metered. No production,
employer data, purchases, publication or irreversible external changes. Continue
bounded validation; Nov30 remains continue/pivot/stop review, not a delivery promise.
