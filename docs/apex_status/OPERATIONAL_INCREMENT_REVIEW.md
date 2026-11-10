# Operational increment review — 2026-11-10

Entry HEAD `9f2a920`, branch `apex/four-layer-owp-integration`; only the uploaded
ZIP was untracked. A subsequent founder instruction arrived during implementation;
Git was checked again and the only additional files were this increment's work.
No newer external implementation was overwritten. Current code, checkpoint,
night report, architecture/kit decisions, inventory and security findings were
reviewed. Baseline rerun:135 passed, two optional web tests skipped.

This is implementer self-review plus executable adverse checks, **not independent
code or semantic review**. No independent reviewer or fresh independently graded
utility cases were available. These acceptance dependencies remain open.

## Five reference defects: containment versus implementation

The reference ZIP is immutable and still reproduces all five defects. It is not
the runtime. The current implementation now addresses the corresponding behavior:

| Defect | Current control | Reproduction/test |
|---|---|---|
| Worker ignores stop | Durable queue state checked at submission, claim and immediately before fixed handler inside its transaction | JobTests.test_every_stop_persists_and_blocks_before_handler; actual stopped CLI call denied |
| Stale attempt acknowledges new lease | Random attempt token, worker identity and strict expiry checked transactionally; same worker name cannot reuse old token | test_reclaimed_same_worker_has_new_token_and_exact_expiry; two-process contention test |
| State commits without audit | Submission, claim, control, terminal state and events share transactions; workflow result and job completion share outer transaction/savepoints | injected audit failures at submit/claim/finish; process exits during completion and recovery verifies rollback |
| Non-finite cost admitted | Existing hard-zero integer policy retained; queue revalidates Task before state mutation | test_finite_budget_and_exact_queue_counts_fail_before_state; current kernel policy regression |
| Fractional coverage admitted | Existing strict counts and hashed snapshot membership retained; source parser rejects bool/non-integral totals | CoverageTests.test_missing_snapshot_items_and_fractional_counts_rejected; SourceTests schema cases |

## Actual component path

Public GET attempt -> size validation failure receipt -> local evidence Case/Task
-> durable jobs table -> fixed existing workflow -> critic blocks unsupported
upstream-fault inference -> journal decision -> matching job receipt -> read-only
report. Input: `examples/contracts_finder_blocker_workflow.json`. The observation
is an actual adapter failure, not synthetic market data. Its time is the local
receipt file mtime, not upstream publication time. No raw notices were retained.
The source URL identifies the attempted source; publisher explicitly identifies
the local observer. Neither this link nor its digest authenticates upstream facts.

`operational_cli_e2e.json` records eight separate process invocations. The job is
COMPLETE because processing finished; workflow status is BLOCKED_PENDING_EVIDENCE.
The second worker invocation is EMPTY. No inference, model or version is promoted.

## Boundaries and residual risks

- Queue is a local SQLite development capability, not a deployed 24/7 worker.
  The only handler is the existing evidence workflow. No user callback, SQL,
  shell, network dispatch or external action handler can be supplied by a job.
- Max100 active jobs, max1000 retained jobs, max262144 payload bytes, max3 attempts,
  leases15–300 seconds and bounded backoff. Reaching retention capacity blocks
  new jobs; there is no automatic deletion. Journal-wide archival remains future.
- Stop is graceful/serialized: a dispatch already holding the write transaction
  finishes or rolls back before a concurrent stop can commit. SQLite lock timeout
  can reject a control request; a rejected request is NOT a successful stop.
  This does not revoke credentials or stop unrelated processes/connectors.
- Local operator CLI can explicitly resume RUNNING. It is not an owner identity
  provider or proof that a remote caller is human. Same-user Python/SQLite remains
  trusted; production privilege separation and authenticated control are absent.
- Unhandled job failure leaves a durable lease for recovery. Caught workflow
  failure/denial becomes a terminal report, not an automatic repeated experiment.
  Changed kernel code prevents dispatch; review and resubmit a new task/job ID.
- New tables are additive (`job_meta` v1 and `jobs`); existing events are retained.
  Job events extend the journal kind set. Before initializing the actual dev queue,
  a private SQLite backup was saved under ignored work/pre-jobs-20261110/.
- Source transport is separately explicit and is not wired to the worker. Its
  live compatibility gate failed; see PUBLIC_SOURCE_ADAPTER.md. No actual market
  packet, independent demand, income or full-domain acceptance was produced.

## Evidence and utility

Full regression:162 passed, two optional FastAPI/httpx integration skips. Positive,
negative, two-process contention, hard process exit/lease recovery, nested rollback,
SSRF/DNS/redirect and subprocess timeout cases ran. These tests were authored by
the implementer; they are regression evidence, not independent holdouts.

The complete conventional policy checklist still matches24/24. Reference failures
versus current controls demonstrate repaired contracts, not intelligence advantage.
CLI elapsed times are recorded, but no independently defined manual task was
timed or rated. Real utility versus an independent baseline is **NOT MEASURED**.
Next trial requires a separate reviewer, identical evidence/time/access, fresh
cases, raw outputs and correction-time measurements. No fabricated scores appear.
