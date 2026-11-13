# Quarantine

Files moved here are NOT committed to the live codebase and must never be imported, run, or
restored into `core/apex/` or `scripts/` without a full rewrite through the existing
ActionGateway/Budget/Ledger pattern.

## bank_agent.py.DANGEROUS_DO_NOT_USE

Found untracked in `core/apex/bank_agent.py` on 2026-11-13. Characteristics:
- Raw `requests.get()` calls to `api.starlingbank.com` with a bearer token read directly from
  an environment variable - no injectable transport (unlike the reviewed `core/apex/starling.py`,
  which is read-only, transport-injectable, and explicitly labeled TESTS_NOT_RUN/NOT_CONNECTED).
- No Budget, no ActionGateway, no ApprovalBook - a live financial-data pull with zero spend
  control and zero human approval gate.
- Writes directly, via its own raw `sqlite3.connect(DB_PATH)`, into
  `runtime/kernel.sqlite3` - the SAME FILE the hash-chained Ledger uses - completely outside the
  Ledger's own transaction/audit discipline. A write from this script could corrupt or silently
  bypass the Ledger's integrity guarantees.
- Matches the exact pattern of the externally-injected code the owner identified and blocked
  this session (see scripts/worker_loop.py's own restoration notes: an earlier corrupted revision
  of worker_loop.py called this exact file via `subprocess.run`).

This was never wired into anything live (confirmed: only `scripts/worker_loop.py`'s own
docstring, describing the past incident, mentions the filename - no executable code path calls
it). It is kept here, inert, only as evidence of what was found and removed - never as a starting
point. The reviewed path for real Starling data is `core/apex/starling.py` plus a real
ActionGateway `KindSpec`, a priced Budget SKU, and an ApprovalBook-gated proposal, same as every
other paid or sensitive capability in this project.

## swarm_api.py.DANGEROUS_DO_NOT_USE / swarm_worker.py.DANGEROUS_DO_NOT_USE

Found untracked at repo root on 2026-11-13 - already identified as the "swarm_worker.py/
swarm_api.py incident" earlier in this session's history, but the files themselves were never
actually removed from disk until now. Characteristics:
- `swarm_worker.py`: a raw `anthropic.Anthropic(api_key=...)` client reading the production key
  file directly, with NO Budget/ActionGateway/ApprovalBook anywhere - completely uncapped LLM
  spend outside the project's zero-budget-by-default discipline.
- Both files read/write a `swarm_status` table via their own raw `sqlite3.connect(...)` calls
  straight into `runtime/kernel.sqlite3` - the same file the hash-chained Ledger owns - bypassing
  its transaction/audit discipline entirely (the exact same risk as `bank_agent.py` above).
- `swarm_api.py` serves that data over plain `http.server` with
  `Access-Control-Allow-Origin: *` (world-open CORS) and no auth.
- Confirmed NOT currently running (no live process, no systemd unit references either file) and
  not imported by anything live. `deploy_final.sh`'s own comment already documents that
  `scripts/orchestrator.py`'s real `agent_telemetry()` reads only the legitimate
  `agent_schedule`/`events` tables "AgentRunner already writes correctly" specifically to avoid
  this file's write path - so the real replacement already exists and is in use.

Kept here only as evidence, same rule as bank_agent.py: never restored, never imported.

## youtube_agent.py.DANGEROUS_DO_NOT_USE (was scripts/youtube_agent.py)

Found untracked at `scripts/youtube_agent.py` on 2026-11-13 - a different file from the reviewed
`core/apex/youtube_agent.py` (read-only channel-analytics snapshot, `youtube.readonly` scope
only, TESTS_NOT_RUN/NOT_CONNECTED, committed this same pass). This one requests the full
`youtube.upload` scope, runs its own local OAuth consent flow with no owner review step, and
uploads a video directly via `youtube.videos().insert()` with no Budget, no ActionGateway, no
ApprovalBook - a live write/publish action with zero spend control and zero human approval gate,
plus Persian inline comments matching the other externally-injected files quarantined above.
Confirmed not imported or referenced by anything live.

## apex_algorithms.py.DEMO_NOT_REAL (was scripts/apex_algorithms.py)

Found untracked at `scripts/apex_algorithms.py` on 2026-11-13 - a standalone demo script, not
wired into anything, not called by anything (confirmed by grep). Three toy pieces in one file:
(1) a sentence-embedding "dating/job match" demo run against four hardcoded fake profiles
(one deliberately caricatured: "Looking for a wealthy man who can take care of me"); (2) a
`networkx` social-graph centrality demo on fabricated names ("Ali", "Friend_A", ...); (3) a
`RandomForestClassifier` "stock prediction" toy trained on one month of AMD data via `yfinance`,
printing a bare "Stock Prediction Model Accuracy: X%" with no backtest, no holdout discipline,
and no caveat - exactly the kind of fabricated-looking-real capability metric this project's own
dashboard work this session explicitly rejected (see SUPERIOR_OS_PLAN_20261113.md Section 3).
No Budget/ActionGateway anywhere; pulls live Yahoo Finance data with no cap. Kept here as
evidence of what was on disk, not as a starting point - any real semantic-matching or
forecasting capability would need to go through agents_impl.py/agents_research.py's existing
claims+evidence+confidence contract, not a bare printed percentage.
