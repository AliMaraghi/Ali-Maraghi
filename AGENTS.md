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
