# Superior OS — brutal-honest status and the real A→Z path (2026-11-13)

## 0. The question asked

"Argue your work comprehensively, brutal honest — not three recommendations — write
A to Z how to reach the superior OS, practical, no blockers, no excuses."

This document does that. Section 1 is the honest inventory (not the pitch). Section 2 defines
what "superior OS" has to mean in measurable terms, because without a definition "no blockers"
is not answerable. Section 3 explains, with specific incidents from this project's own history,
why some constraints are not excuses — they are the difference between a system that works and
one that silently lies to its owner. Section 4 is the actual A→Z plan: every step is something
that can start today, with no invented blocker, inside this exact repo. Section 5 is the short
list of things that will never be built regardless of how the request is phrased, and why that
list is not padding.

## 1. Brutal-honest inventory, right now

Measured directly against this repository at commit `5dea89a`, not against the manifesto's
ambition:

- **4 of 18 declared agent roles run real code.** `core/apex/agents_governing.py` lists 18 role
  rows; exactly 4 are marked `IMPLEMENTED_LOCAL` (A-1 Strategic Intelligence, A-2 Scientific
  Research, A-5 Career & Industry, A-8 Financial Intelligence). The other 14 are `SPEC_ONLY` —
  description text, no running logic, no tests, nothing that executes.
- **20 of 24 legacy registry entries have an unknown real identity.** `core/apex/agents_registry.py`
  was destroyed by an external, unreviewed tool earlier this session and had to be rebuilt from
  test assertions alone. 20 entries are marked `PLACEHOLDER` in their name/description field
  because the actual intended identity of those slots is genuinely not known — it was never in
  git, so there is no way to recover it. This is not a cosmetic gap; it means roughly 80% of the
  "18-role roster" referenced throughout the manifesto has no verified definition today.
- **107 of ~131 Python files in this working tree are untracked by git**, including
  `bank_agent.py`, `starling.py`, `monzo.py`, `telegram_bot.py`, `twitter_agent.py`,
  `youtube_agent.py`, `pubmed.py`, `gmail_drafts.py`, `outlook_graph.py`, `bridge_server.py`,
  `bridge_auth.py`, `bridge_queue.py`, `bridge_web.py`, `approvals_web.py`, `health_labs.py`,
  `decision_twin.py`, `relationship_assist.py`, `social_snapshots.py`, `location_coarse.py`,
  `chat_import.py`, `ffmpeg_plan.py`, `private_token.py`, and five `core/apex/kernel/*.py`
  modules (`adapters.py`, `approvals.py`, `budget.py`, `dossier.py`, `facts.py`, `gateway.py`,
  `temporal.py`). Before this session's single commit, **none of this had version history** — no
  diff review, no rollback point, no way to prove what changed between two points in time. That is
  the single biggest real risk in this codebase today, bigger than any missing feature: a second
  external corruption event (which has already happened twice to `worker_loop.py` and once,
  unrecoverably, to `agents_registry.py`) could destroy any of these 107 files with no way back.
- **11,182 lines of `core/apex` code** against **7,280 lines of test code** (63 test files) — a
  healthy ratio for what is tested, but it only covers the 4 implemented agents plus the kernel
  primitives (Ledger, Budget, ApprovalBook, Gateway, facts). The 14 `SPEC_ONLY` roles and most of
  the 34 untracked integration modules (`bank_agent.py`, `telegram_bot.py`, `twitter_agent.py`,
  etc.) have little or no real-API verification — several were written, offline-tested with
  mocks, and never exercised against the live service they target.
- **Every "this was caught by running it for real" bug this session** (the `claude-haiku-5-5`
  thinking-block failure that broke every LLM-calling agent despite 100% mocked tests passing;
  the `setup_espp.py` mortgage-multiplier unit-conversion bug; the `UnboundLocalError` in
  `dashboard_payload`) was invisible to the test suite and only found by hitting the real API or
  running the real script. That is the actual current ceiling on "how much do we really know this
  system works": roughly as much as has been manually, individually verified against live
  behaviour — a small fraction of the code that exists.

None of this is a reason not to go further. It is the actual starting line. A plan that doesn't
start here is not honest.

## 2. What "superior OS" has to mean to be buildable

"Superior" is not a target you can build toward; it has no done condition. The manifesto's own
18-section ambition has the same problem at a larger scale. A buildable target needs numbers:

A **personal operating system** for one owner is superior, in a way that can be checked rather
than asserted, when it satisfies all of:

1. **Breadth with evidence**: N of 18 roles are `IMPLEMENTED_LOCAL`, each with its own test suite
   and at least one real (non-mocked) run logged in the Ledger.
2. **Calibration with evidence**: for each role that makes a recommendation, there is a
   non-empty `fact_outcomes` history, and a documented, re-run comparison showing the
   recommendation changed as a measurable result of that history (the finance calibration built
   this session is the first instance of this — one role, not eighteen).
3. **Autonomy within a provable boundary**: any action that leaves the local Ledger (a message
   sent, a post published, money moved) requires a human-approved proposal through the existing
   Gateway, with 100% of such actions traceable to an approval row — zero exceptions, checked by
   a test that asserts there is no code path around `ActionGateway.execute()`.
4. **Reliability with evidence**: the worker/scheduler processes have a measured uptime and a
   measured mean-time-to-recovery after an induced failure (already started —
   `WORKER_OPERATIONS_REPORT.md`'s exit-78/recovery work — but only measured for one process, not
   the whole system).
5. **Honesty with evidence**: every number the owner-facing dashboard shows is traceable to a
   real file, a real Ledger row, or a real computed value — never a static or illustrative
   number — checked by a test, the same discipline already enforced for the finance card this
   session.

Under this definition, "superior" is a vector that moves one role, one test, one real run at a
time. There is no single architectural change that produces it, and no plan that promises one
would be honest.

## 3. Why the existing constraints are not excuses

Each of these has already caused or prevented a real, specific, named failure in this project.
Removing any of them does not remove a blocker — it reopens an incident that has already
happened once.

- **No action without a human-approved Gateway proposal.** This is what stopped a draft research
  brief, a tweet, a dating-opener draft, and the new capability-proposal mechanism from ever
  being sent/posted/adopted automatically. Without it, the `bank_agent.py` incident this session
  — a raw Starling bearer-token call running as a subprocess completely outside Budget/Gateway —
  would have been a live, unbudgeted, unreviewed financial action instead of a corrupted file
  that got caught and reverted.
- **Zero-budget-by-default on every LLM call.** This is what makes `llm_route`, `llm_plan`, and
  `propose_capability.draft_capability` safe to leave switched on: an unpriced SKU means the
  call silently returns `None`/raises `BudgetDenied` instead of spending. Removing it means every
  new LLM-touching feature is a live financial liability the moment it is deployed, not after a
  deliberate pricing decision.
- **No fabricated metrics.** The `dashboard_payload` fix earlier this session replaced a
  claims-count placeholder with the real last-computed finance figure specifically because a
  fake-looking-real number is worse than an honestly-absent one — it would have told the owner
  something false with full confidence. A "superior OS" that reports invented health scores is
  not superior, it is a system that has started lying to its own operator, which is the actual
  failure mode "superintelligent" is usually used to wave away.
- **Controlled evolution (propose → human review → manual test/adopt, never auto-deploy).** The
  capability-proposal mechanism built this session deliberately stops at "propose a draft." A
  system that drafts, sandboxes, tests on held-out cases, and only then proposes promotion through
  the existing deployment path with a reversible artifact is a legitimate and currently unbuilt
  next step (Phase F below). A system that writes its own code and deploys it with no review step
  is not a more advanced version of this project — it is the precondition for the exact kind of
  silent corruption that already destroyed `agents_registry.py` once this session, except
  self-inflicted instead of external.
- **Git discipline / no destructive ops without confirmation.** Given that 107 files are
  currently unprotected by any version history, any argument for skipping this is an argument for
  repeating the `agents_registry.py` loss, except for a much larger surface area.

None of the above blocks adding capability. All of them are satisfied by the plan in Section 4.

## 4. The A→Z plan — practical, sequenced, each step startable today

Each phase lists its real deliverable and its real exit condition — not vibes. Phases A–C are
infrastructure debt that makes everything after them actually trustworthy; skipping them to reach
"impressive" faster is exactly how the two `worker_loop.py` corruptions and the `agents_registry.py`
loss happened.

**A. Stop the bleeding: commit everything real.**
Deliverable: every file in the 107-untracked list reviewed file-by-file (diff against nothing,
since there is no prior version — this is a one-time read-through) and committed in small,
reviewed batches, oldest/most-depended-on first (`kernel/*.py` → `agents_*.py` → integration
modules → deploy scripts). Dead, abandoned, or duplicate files (`console_server.py.bak`,
`deploy_*.sh.save`, stray `deploy_*.sh` variants) get explicitly deleted, not silently kept.
Exit condition: `git status` shows no untracked `.py` file under `core/` or `scripts/` that is
still imported by anything live.

**B. One integration module at a time, through the existing Gateway — never a new side door.**
Deliverable: for each of the 34 untracked integration files (Starling, Monzo, Telegram, Gmail,
Outlook, Twitter, YouTube, PubMed, bridge_*), either (a) it gets a real test suite, a priced
Budget SKU if it calls anything paid, and a Gateway `KindSpec` with `adapter=None` or a real,
reviewed adapter — then one real (not mocked) end-to-end run against the actual service with the
owner's own credentials, logged in the Ledger — or (b) it is archived as not-yet-ready, clearly
labelled, with no code path that can execute it. No module goes live by just existing in the
directory.
Exit condition: every file in `core/apex/` either has a passing test suite plus one logged real
run, or is explicitly archived.

**C. Promote SPEC_ONLY roles to IMPLEMENTED_LOCAL one at a time, same discipline as A-1/A-2/A-5/A-8.**
Deliverable: pick the highest-value SPEC_ONLY role next (owner's call — likely whichever of the
14 placeholder roles maps to a module already built in Phase B), give it a real `AgentResult`
contract, real claims with evidence IDs, a real test suite, and wire it into
`agents_runner.py`'s agent list the same way the existing four are wired.
Exit condition after each role: `agents_governing.py` flips that row to `IMPLEMENTED_LOCAL`, with
a passing test suite as the only thing that justifies the flip (never flipped speculatively).

**D. Make `_CAPABILITY_REGISTRY` grow through the proposal pipeline, not by hand only.**
Deliverable: this session's `propose_capability.py` becomes the standard on-ramp for new voice
capabilities — any repeated `capability_gap` fact (tracked via `facts.fact_history`) with 3+
occurrences triggers an owner-visible reminder (not an automatic proposal — a reminder that the
gap keeps recurring) to review the pending draft already sitting in the ApprovalBook.
Exit condition: at least one capability added to the registry this way, end to end, with the
owner's own review and manual wiring as the final step (per Section 3 — this step stays manual).

**E. Close the outcome-calibration loop for every domain, not just finance.**
Deliverable: the pattern built this session for `finance_claim_*` (`recent_outcomes_for_predicate_prefix`
feeding back into the next recommendation) gets repeated for each IMPLEMENTED_LOCAL role that
makes a recommendation (A-1's scenario calls, A-5's shortlists, any new role from Phase C) —
same fact-store mechanism, no new infrastructure needed, only new call sites plus
`scripts/record_outcome.py` becoming a genuine daily habit.
Exit condition: a measurable, before/after example (like the test already written this session)
exists for at least 2 more domains.

**F. Real controlled evolution: sandboxed test, not just draft.**
Deliverable: extend `propose_capability.py` so an APPROVED `capability_proposal` can be run
through a genuinely isolated evaluation — no network, no secrets, bounded CPU/time, executed in
a subprocess with its own restricted interpreter — against held-out synthetic cases the owner
defines, producing a pass/fail report attached back to the same proposal row. Promotion into
`_CAPABILITY_REGISTRY` remains a manual step even after a pass — the sandbox proves "doesn't
crash on these cases," never "safe to auto-deploy."
Exit condition: one proposal taken all the way from draft → sandboxed test report → owner-reviewed
manual adoption, with every step logged.

**G. Reliability: measure it instead of asserting it.**
Deliverable: extend `WORKER_OPERATIONS_REPORT.md`'s exit-78/recovery discipline to every
long-running process (`apex-agents.service`, `apex-bridge.service`, the voice API), with a real
uptime/restart-count log reviewed weekly, not just unit-file correctness at a point in time.
Exit condition: 7 consecutive days of real uptime numbers for every production unit, logged, not
estimated.

**H. Dashboard: finish making every number traceable.**
Deliverable: apply the same fix this session made to the finance card (`dashboard_payload`
querying a real fact instead of a claims-count placeholder) to every remaining card — job
shortlist count, academic feed freshness, dating-draft readiness — until none of them show a
number that isn't a direct read of a real file or Ledger row.
Exit condition: a test for every dashboard card asserting it reads real state, matching the
existing `DashboardRealFinanceMetricTests` pattern.

**I. Security/compliance hardening already in flight — finish it, don't restart it.**
Deliverable: continue `ACCESS_ORIGIN_REPORT.md`'s owner-view JWKS validation and
`HOST_DEPLOYMENT_BOUNDARY.json`'s PolicyKit findings to an actual supervised, Access-fronted
deployment — this is infrastructure debt, not new architecture, and it's already partly done.
Exit condition: a real external request through Cloudflare Access reaching `/console` with
RS256 owner-identity validation, observed live, not asserted.

**J. Re-measure against Section 2's five criteria.**
Deliverable: after A–I, recompute the same numbers as Section 1 (N of 18 roles implemented,
outcome-calibrated domains, uptime, dashboard honesty). The comparison between this document's
numbers and that re-measurement is the actual evidence of progress — not a new adjective.

## 5. What stays out of scope regardless of framing — and why that's not padding

- **Auto-deployed, self-written code with no human review step.** Phase F's sandbox proves
  "didn't crash" — it never proves "safe," and nothing in software engineering makes an
  automated test suite a substitute for review before something runs against real accounts, real
  money, or real messages sent in the owner's name.
- **Fabricated success/health/trust metrics of any kind.** Already covered in Section 3 — this
  is not a style preference, it is the dashboard bug this session already found and fixed once.
- **External write actions (sending, posting, paying, applying) without the owner's explicit,
  per-action approval.** This is the entire reason the Gateway/ApprovalBook exists, and the
  entire reason the `bank_agent.py` subprocess incident was recoverable instead of catastrophic.
- **Demographic profiling/targeting for solicitation, controlled-substance sourcing, or any other
  line already drawn earlier this session.** Unchanged by this document; restated here only for
  completeness.

Nothing above is an "excuse" in the sense of avoiding work. Every item in Section 4 is real,
scoped, startable work. The five items in this section are the only permanent no — everything
else is a sequence of Tuesdays.
