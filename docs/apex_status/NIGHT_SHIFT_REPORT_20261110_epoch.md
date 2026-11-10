# Night engineering checkpoint — 2026-11-10

Status: TESTED_OFFLINE increment; complete APEX NOT ACCEPTED. Work stayed in
/home/apexdev/apex-work. No production, accounts, employer data, deployment,
network retrieval, purchases or paid API calls. No new subagents used.

## Code and Git

Entry HEAD bcde451; branch apex/four-layer-owp-integration. Commit 0cb89f8 saved
bounded workflow/replay and read-only report functionality before reference
integration. Latest implementation commit is recorded in CHECKPOINT.json and
`git log`; the local completion log references that commit without changing it.

Code added/adapted: core/apex/kernel/owp.py, CLI owp-plan and owp-coverage,
tests/test_owp.py, traceability export and both-six-set tests. The prior workflow
joins evidence checks, opposing template hypotheses, criticism, fail-closed
status and durable replay in one local transaction; it cannot promote a version.

OWP accepts arbitrary bounded axes/source candidates; no fixed country/sector
idea list. It strictly validates all inputs, caps source/probe space, reports
omitted pairs and rejects spend/expired/stopped requests. Coverage verifies local
snapshot hashes, integral counts and inspected/selected ID membership. It never
claims source completeness, actual inspection, market gap or demand verification.
The source candidate registry is metadata only; no connector is enabled.

Recovery script backs up/reopens one synthetic journal and compares exact records.
No DB schema changed. Existing verified evidence, economics, lab receipts, domain
planning, scheduling specification and studio exports were retained.

## Kit reconciliation

Archive SHA-256: 611ff49f1e68e33e0e1f69fafb464ae9ea382b1d03ced4c5e6add497913a4a67.
48 files reviewed, CRC valid, 47/47 manifest checksums match. All five requested
review docs copied unchanged into docs/. Every import/defer/reject decision and
file hash is in REVIEW_KIT_INVENTORY.csv / REVIEW_KIT_DECISIONS.md. Original
manifesto remains 3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd.

Reference's 69 tests pass, but five new synthetic probes reproduce: worker bypasses
STOP_EXECUTION, stale attempt can finish reclaimed lease, task commits without
audit event, NaN cost allowed, fractional counts treated as coverage. Rejected
these runtime imports; preserved stronger existing implementation. Advertised
APEX_EPOCH_ENGINEERING_V1/prototype/apex_reference/ is absent; actual code is in
APEX_EPOCH_ENGINEERING_V1/apex_epoch/. Uploaded ZIP remains untracked/preserved;
reference extraction is ignored work/review-kit/, never production or installed.

## Observed verification

- Current suite: 135 passed, 2 optional FastAPI/httpx integration skips, 0 failures.
- Kit suite: 69 passed. Adverse probes: five defects reproduced (not five passes).
- Source trace: 178 groups, 968 source units, all 0–18/appendices/18 roles/A01–A09;
  both canonical and historical six §5 sublayers remain separately addressable.
- Original hashes: all 13 listed entries match. Syntax parsing and edited-code/generated-document whitespace pass; five original
  Markdown hard-break lines in the copied founder directive remain byte-preserved.
- Synthetic policy benchmark: candidate24/24, weakrule13/24, fullchecklist24/24.
  Already seen cases, no independent holdout or model superiority; no promotion.
- OWP CLI examples: two unexecuted probes; two snapshot IDs/one declared inspected.
- Local synthetic backup/restore: one event reopened identically; not production
  MTTR, encrypted/offsite recovery or service availability evidence.

Exact commands/results/report hashes: TEST_EVIDENCE.csv. Benchmark methodology
and timings: MEASURED_BENCHMARKS.csv and reports/validation/epoch_policy_benchmark.json.
Original failed workflow run was preserved before fixes in override_tests_first_failure.txt.
Full file changes: `git show --stat` and `git diff bcde451..HEAD --name-only`.

## Honest remaining gaps and decision

No real opportunity packet/customer validation/income, no authorized film assets
or rendered movie, no direct-model/human comparison, no encrypted private memory,
authenticated mobile command plane, operational queue/global stop or deployed
runtime. Source-line retention is not complete independent semantic atomization.
Workflow time limit is cooperative, not preemptive. URL validation is parse-only;
all network adapters remain absent. All 18 full-domain acceptance gates stay open.

Additional paid API spend GBP0/USD0; hosting/subscription/time not separately
metered, total cost unknown. Continue bounded validation toward Nov30; pivot/stop
if an independent same-input comparison cannot show useful value over a checklist.
See NEXT_ACTION.md, ARCHITECTURE_DECISIONS.md and RECOVERY_RUNBOOK.md to resume.
