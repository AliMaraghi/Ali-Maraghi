# Development decisions and execution history

## 2026-11-09 — preserve before implementation

Observed working sandbox, read full authoritative sources, audited the existing
application and previous RDE ZIP/report. All source checksums matched. Initialized
the missing local-only Git repository as required by the mission; `61adae7`
preserves originals and prior report. No remote, deployment or service access.

## 2026-11-09 — one local kernel

Chose typed standard-library Python and SQLite over new queues, paid models or
agent services. The bounded task is auditable decisions and rejection of invalid
evidence/actions. Conventional automation remains a strong baseline; no claimed
advantage over ChatGPT, Claude, Codex or a human reviewer.

Added strict case/evidence contracts, artifact checks, separate deterministic
critic, zero-spend gateway, persistent journal, repeatable fixture lab, local
version rejection/promotion/rollback, three domain utilities and reproduction
scripts. Inputs/results and kernel code are fingerprinted. Original documents
are unchanged; sensitive archive text is referenced by hashes and source anchors.

## 2026-11-09 — review and repairs

Fixed mutating health checks, redirect-following feeds, backup permissions and
unbounded/off-workspace legacy JSON reads. Tested locally with mocks rather than
starting Docker or connecting a database.

Kernel review found stale-baseline promotion and generic journal append allowing
promotion events. Fixed both with regression tests. Receipts must have consistent
metrics; comparison must use the current champion. Same-user Python remains a
trusted operator boundary. Tightened empty URI userinfo and malformed sensitivity.

## 2026-11-09 — continuation and test failure

On the founder's resume instruction, inspected saved changes and commits, and
started no new reviewers. The permission scope reset rejected a write; renewed
only workspace/Git access and applied the fix normally. Existing reviewers then
hit their usage limit; parent completed their saved work without paid credits.

First combined run failed because a legacy subprocess lacked PYTHONPATH. Retained
the failed log, fixed explicit child environment, then reran. Final:96 passed,
2 optional integration skips, no failures. The runner includes original
pytest-style RSS functions, which ordinary unittest discovery would omit.

## 2026-11-09 — evidence and operating decision

Frozen synthetic policy cases were authored by a separate reviewer before
execution, but the implementer read them while wiring the runner. They are not
independent real-world validation and are now regression data. Kernel24/24;
minimal rule13/24; full conventional checklist24/24. No candidate was promoted
from this benchmark. Toy promotion/rejection/rollback was tested in isolated DBs.

Continue bounded day-0 validation. Do not broaden architecture or spending without
useful outcomes. Before Nov30, compare real decisions with manual/direct-model
baselines and apply the continue/pivot/stop gate. Future manifesto scope remains
preserved with explicit dependencies and acceptance scenarios.

## 2026-11-10 — preserve working kernel; reconcile founder review kit

Created branch apex/four-layer-owp-integration from bcde451; commit0cb89f8 saved
tested workflow/replay/readonly reporting. Verified all48 kit files and47 checksums;
69 reference tests pass, five newly reproduced negative cases expose unsafe runtime
imports. Rejected reference worker, queue, gateway and database replacement.
Adapted dynamic OWP axes and coverage with strict input bounds/integer counts,
source snapshot membership and explicit unverified states. No new dependencies,
DB schema, network or service. Four logical planes and both §5 six-sublayer sets
are mapped without changing originals. Current135 tests pass; two web skips.
Continue bounded offline validation; no superiority or field value established.

## Operational continuation — 2026-11-10

Resumed9f2a920 and reran135-pass baseline. Designed/tested explicit public adapter;
network permission granted, two attempts blocked by response page-size contract.
No gate relaxed and no actual opportunity packet fabricated. Subsequent founder
instruction prioritised five defects; implemented local durable queue/fencing/
transactional audit around existing workflow, retaining finite budgets/exact counts.
Actual blocked-source receipt ran through CLI queue to durable blocked report.
Final162 passed,2 skipped; crash/competition/security evidence recorded. Independent
review/utility baseline unavailable and explicitly not claimed. No production/spend.

## 2026-11-22 Gmail retention and coverage policy (owner decision)

- Owner instruction in chat, 22 Nov 2026 02:45 UTC, verbatim: "1. Raise it to a fixed larger number (say 2,000 threads), still metadata only."
- Policy as implemented (`core/apex/gmail_sync.py`): metadata only; at most 2,000 threads held, encrypted; the 2,000 is treated as temporary.
- Initial coverage is bounded: newest threads first, stopping when another page would not fit. The receipt then reports
  `coverage.initial_complete = false, stopped = CAPACITY`. Older mail is NOT covered and nothing claims it is.
- After the initial pass, incremental history keeps the set current. If new threads push the count over the cap, the oldest
  are evicted and every eviction is counted in the receipt (`evicted_oldest`). Deleted threads are removed (404 on refresh).
- Existing stored state (the first 100 threads) is preserved; the sync resumes from its saved page token.
- Not decided: full-mailbox backfill, any content beyond headers, or a larger cap. Each needs a new owner decision.
