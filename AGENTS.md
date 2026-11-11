# APEX v4.4 — durable repository directives for Codex

This is a personal research/development codebase, **not a completed AGI**. The 18-section North Star is in `docs/apex_handoff_20261109/APEX_4_4_FINAL_MASTER_MANIFESTO.md` (immutable SHA-256 in mission). Read `docs/apex_handoff_20261109/MISSION_CONTRACT.md` for this development session and `APEX_4_4_ACCEPTANCE_GATE_FA.md` for acceptance details. Do not falsely equate code or unit tests to deployed capability.

Work within the unprivileged dev workspace only. No root/sudo/Docker/production files/paid services/private data/employer systems/external write actions without explicit user approval. Never send credentials or sensitive personal information to logs/commits or public outputs. No public repository. Keep originals unchanged, use reproducible tests, evidence, source links, exact cost accounting and robust holdout benchmark. Prefer implementing and verifying over promising. Persist project state under `docs/apex_status/`, not chat memory. Summarize to user in Persian. Do not ask approval for routine code changes/tests in the workspace.

## Resume protocol (2026-11-09 increment)

Read `docs/apex_status/NEXT_ACTION.md`, `REALITY_BASELINE.md`, `DECISION_LOG.md`
and `21_DAY_SCORECARD.md` before new work. Inspect `git status` and the local log;
baseline snapshot is `61adae7`. Original handoff documents are immutable.
No remote is authorized. Keep runtime journals and scratch files ignored.

Use `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py` for the available
suite. It reports optional web tests as skipped if their dependencies are absent.
Do not run `scripts/verify.sh`, `scripts/run_discovery_once.sh`, the backup script,
the monitor or `--from-db`: these can touch Docker/services/production data.
Use `python3 -B scripts/traceability.py` for source retention and
`python3 -B scripts/benchmark_kernel.py` for the explicitly synthetic benchmark.
See `docs/apex_status/RDE_ARCHITECTURE.md` for CLI commands and trust boundaries.

The kernel has no model/network/account adapters. Its critic checks integrity and
structure, not source truth or independent performance. READY_FOR_HUMAN_REVIEW is
not validated demand. Evolution changes only a local experiment-version pointer;
it never deploys or changes policy. Candidate and baseline must be compared on
fresh evaluation data before operational promotion can even be considered.
All 18 sections, section 0 and appendices remain future requirements where
unimplemented. Do not convert unit-test counts into full domain acceptance.

## Night increment

Read `docs/apex_status/NIGHT_SHIFT_REPORT.md` for the latest evidence. The
`apex.kernel.cli propose` command generates bounded rule-based hypotheses only
from integrity-eligible observations; source labels still do not prove truth.
`kernel/opportunities.py` ranks review priority, never verified economic value.
Lab receipts now require per-case repeated observations; aggregate-only historical
receipts cannot authorize new promotions. Scheduling is dry-run only: no daemon,
worker, network dispatch or persistent global stop control has been enabled.
`apex.studio.edit_package` exports planned script/captions, never a rendered film.

## Four-plane / OWP checkpoint (2026-11-10)

Resume on `apex/four-layer-owp-integration`; read CHECKPOINT.json and the current
NIGHT_SHIFT_REPORT.md. All 48 review-kit files were inspected; five reproduced
reference defects prohibit wholesale runtime import. REVIEW_KIT_DECISIONS.md
and ARCHITECTURE_DECISIONS.md preserve four planes, both six-sublayer §5 sets and
all 18 role slots. Original documents remain immutable. Uploaded ZIP is preserved
untracked; reference extraction is ignored, never installed.

Current tests:135 passed, two optional web integration skips. New OWP CLI commands
prepare bounded searches and inspect hashed local snapshot coverage; they do not
fetch sources or prove demand. Workflow replay returns historical evidence without
freshness revalidation. `scripts/smoke_local_recovery.py` uses synthetic isolated
journals only; no production/offsite restore is established. Do not activate
workers, network adapters or role capabilities from reference flags/booleans.

## Current operational continuation

Latest evidence:162 passed/two optional web skips. Read OPERATIONAL_INCREMENT_REVIEW.md
and current NEXT_ACTION.md. Jobs now persist with fenced leases, stop checks and
atomic workflow/audit; jobs-run-one is manual/local, no daemon or network handler.
Source adapter is separately explicit; live packet BLOCKED because service returned
more than requested size5. Verify current request/licence before further retrieval.
Never broaden caps to pass a source test. Stop is queue-local/graceful, not global
revocation. Current local task cf-diagnostic-20261110-v1 reports blocked evidence,
not verified demand. The unmodified reference still has its five known defects.

## Unified field continuation
Current branch apex/unified-field-integration. Read FIELD_OUTCOME_REPORT.md and NEXT_ACTION.md. Seven real UK notices observed, four unverified candidates (two founder seeds), three excluded; TED schema rejected. Unified entrypoint scripts/apex. No production or paid authority. Preserve original sources and runtime evidence.

TED continuation: read CONNECTOR_INCREMENT_REPORT.md. Trace ted-field-20261110-v2 contains five real notices, three unverified candidates and two exclusions. Latest suite181 passed/2 skipped. No124-provider registry found; no credential storage approved.

Mission runtime continuation: read MISSION_RUNTIME_REPORT.md. missions CLI schedules bounded dependency graphs over existing Jobs; concurrency1, no daemon. Six deterministic review jobs completed from persisted TED trace. This is not independent external verification or qualified commercial advice.184 tests passed/2 skipped.

Recurring schedules: SCHEDULE_INCREMENT_REPORT.md. schedules add/poll/status persists bounded recurrence; no daemon. Evidence expiry is never refreshed by scheduling. Six old mission jobs preserved.191 tests passed/2 skipped.

Activation continuation: read ACTIVATION_INCREMENT_REPORT.md. /console and /reports are authenticated local database projections; worker CLI executable but no persistent service installed. Production authentication/staging credentials unavailable.193 tests passed/2 skipped.

Worker fairness continuation: WORKER_FAIRNESS_REPORT.md;198 passed/2 skipped. worker_dispatch is an additive audited rotating cursor, not a second job queue. cloudflared system service active; origin/Access/TLS and supervised APEX deployment unverified. Preserve old code-fingerprint blocks.

Access origin continuation: read ACCESS_ORIGIN_REPORT.md. owner-view --access-config rejects Basic fallback and validates RS256 owner identity against reviewed expiring JWKS. No live Access binding or production-ready HTTP deployment. Never use fixture keys in production.206 passed/2 optional skips.

Worker operations: WORKER_OPERATIONS_REPORT.md;210 passed/2 skipped. worker_health observations are not deployment proof. Exit78 after3 consecutive failures requires explicit recovery; unit template must retain RestartPreventExitStatus=78. No persistent installation performed.

Provider framework: read PROVIDER_FRAMEWORK_REPORT.md. Crossref live trace crossref-20261110-v1 has3 metadata records; not scientific truth.217 run/215 pass/2 skips. Existing FTS/TED preserved. Catalog not authoritative130 inventory. No arbitrary host or OAuth authority; ambiguous provider attempts never auto-retried.

Host boundary correction: HOST_DEPLOYMENT_BOUNDARY.json. PID1=codex, host cloudflared PID invisible, host bus readable. PolicyKit manage-units/manage-unit-files/reload-daemon returns false with challenge available. Use approved host authentication, never self-SSH/namespace escape. Do not repeat unchanged sudo attempts.

Google additive directive: GOOGLE_SYNC_REPORT.md and GOOGLE_REQUIREMENTS.json. Gmail encrypted sync engine tested offline with injected client only; no live Google binding. Never copy ChatGPT tokens or private mail into public ledger.220 passed/2 skips.

Product continuation2026-11-11: PRODUCT_DELIVERY_20261111.md/PRODUCT_ACCEPTANCE_20261111.json.12section bilingual command centre, source projection, Access-only Waitress origin.231regressionpass/2skip+11bundlepass. Browser realledger localtest, not production/Safari. Host apply now requires python3 -I; do not publish before real Access tests.

Google package request: GOOGLE_PACKAGE_REVIEW.md. New ZIP not found; no integration claimed. Existing explicit Ledger transactions retained; ciphertext/audit/cursor rollback verified. Header allowlist enforced.234pass/2skip. No live import until explicit policy review and OAuth/key binding.

Google rebuilt addon received/reviewed: GOOGLE_ADDON_INTEGRATION.md.12files/11hashes,26reference tests. Reference token/audit defect reproduced; no wholesale import. Strict import policy + session-bound encrypted PKCE state use existingLedger.240pass/2skip. OAuth unmounted; no live data. Previous missing-package blocker resolved.

New apex-google.zip reconciled: GOOGLE_ZIP_RECONCILIATION.md. All12members identical to prior rebuilt addon; no new source delta.3ee9730 remains implementation commit.240projectpass/2skip,26referencepass,11bundlepass. Do not re-import excluded reference modules.

Three-track continuation: THREE_TRACK_INCREMENT.md, BANKING_INCREMENT.md and
META_INCREMENT.md. Google token broker/exchange/controller implemented but HTTP
routes, session auth and scheduler wiring not mounted. Partial bank and Meta
adapters use same Ledger and show AUTH_REQUIRED; no live private connections.
Never infer host executor access from an opened IONOS browser tab.

Unified web continuation: UNIFIED_WEB_INCREMENT.json. Conditional Google routes
use existing Access-only console, private config, token-bound sessions and CSRF.
Pinned console unit now allows only runtime writes. No host installation or live
consent; manual bounded sync only. Never equate mounted code with deployed routes.

Connector schedule continuation: CONNECTOR_SCHEDULE_INCREMENT.json. Gmail recurring sync
uses existing Schedules/worker/Ledger via fixed allowlisted handler and opt-in worker
drop-in; default worker unit unchanged. 276 run/274 pass/2 skip. Not deployed; PID1 systemd.
