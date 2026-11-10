# Review kit compatibility decisions — 2026-11-10

Archive: `APEX_EPOCH_ENGINEERING_V1.zip`; SHA-256 `611ff49f1e68e33e0e1f69fafb464ae9ea382b1d03ced4c5e6add497913a4a67`.
All 48 files inspected: 47 manifest checksums match; ZIP CRC valid. Checksums prove internal consistency, not an independently signed publisher identity. Each file, hash and disposition is in REVIEW_KIT_INVENTORY.csv. Byte-identical canonical sources reuse the recorded full reading rather than inventing a new historical version.

Integration branch: `apex/four-layer-owp-integration`. Founder-observed HEAD `bcde451` was correct at entry; `0cb89f8` preserved the tested workflow increment before kit integration. No reset, new checkout, dependency install or production access. The uploaded ZIP stays untracked and unchanged; extracted reference stays under ignored `work/review-kit/`. No apex_epoch package is installed or imported by the application.

All five mandatory review documents are now present at their exact `docs/` paths. The directive mentions `prototype/apex_reference/`, which is ABSENT from this ZIP; actual package path is `APEX_EPOCH_ENGINEERING_V1/apex_epoch/`. No content was invented for that absent directory.

## Reproducible adverse findings

`python3 -B scripts/audit_review_kit.py --probe-reference` reproduces five findings using only synthetic in-memory databases. The archived 69-test suite passes despite these gaps. Results: `reports/validation/review_kit_audit.json`.

| File | Decision | Reason |
|---|---|---|
| .gitignore | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| AGENTS.md | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| PACKAGE_SHA256SUMS.txt | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| README.md | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| VERSION | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| apex_epoch/__init__.py | NO_IMPORT | No competing package imported into runtime. |
| apex_epoch/__main__.py | NO_IMPORT | Keep apex.kernel.cli entrypoint. |
| apex_epoch/budget.py | REJECT_RUNTIME | Current hard-zero gate retained; arbitrary ceilings and weak numeric typing unnecessary for current authority. |
| apex_epoch/cli.py | RETAIN_EXISTING | Extend current CLI, no second runtime or arbitrary database-path option. |
| apex_epoch/constitution.py | RETAIN_EXISTING | Existing 178 groups/968 source units more detailed; four-plane crosswalk added without replacing source registry. |
| apex_epoch/coverage.py | ADAPT_AND_HARDEN | Require integral counts, hashed snapshot membership, dated records; no full-market claim. |
| apex_epoch/database.py | REJECT_RUNTIME | Keep existing Ledger; separate mutation/audit transactions and incompatible schema/path; no migration. |
| apex_epoch/eval_lab.py | RETAIN_EXISTING | Caller-supplied scores/independence flags are not independent proof; current per-case repeatable receipt is retained. |
| apex_epoch/evidence.py | RETAIN_EXISTING | Current byte/hash/excerpt and reference checks stronger; partial immutable-row comparisons and declared publishers insufficient. |
| apex_epoch/identity.py | DEFER | No private memory adapter; declaration-based public flags are not DLP or consent authority. |
| apex_epoch/media.py | RETAIN_EXISTING | Existing byte-level authorized asset checks and script/SRT workflow retained; kit tests no actual rendered asset. |
| apex_epoch/models.py | RETAIN_EXISTING | Strict current JSON/schema retained; reference canonical default=str and loose enum/number checks not adopted. |
| apex_epoch/ops.py | RETAIN_EXISTING | Current health and dry-run scheduling retained; static readiness is not operational monitoring. |
| apex_epoch/owp.py | ADAPT_CONCEPT | Bounded dynamic axes adapted in kernel/owp.py; reject unbounded iterables, delimiter identity and weaker evidence/economics. |
| apex_epoch/planner.py | DEFER | DAG proposal useful future concept; enabled_roles caller set not authority, cost lacks strict type validation. |
| apex_epoch/policy.py | REJECT_RUNTIME | Reproduced NaN cost acceptance; unauthenticated human string/boolean is not owner authentication; preserve stricter local gateway. |
| apex_epoch/rde.py | RETAIN_EXISTING | Existing proposals gate on actual eligible local artifacts; templates in either runtime do not establish novelty. |
| apex_epoch/roles.py | DEFER | 18 roles already traced; booleans and proof_ref string cannot establish executable independent capability. |
| apex_epoch/security.py | RETAIN_EXISTING | Both URL validators parse only; no network/DNS authority. Keyword markers do not stop injection. |
| apex_epoch/worker.py | REJECT_RUNTIME | Reproduced execution under STOP_EXECUTION; trusted-handler binding alone is insufficient. |
| apex_epoch/workqueue.py | REJECT_RUNTIME | Reproduced stale-attempt acknowledgment and unaudited committed state; no stop enforcement. |
| docs/ACCEPTANCE_A01_TO_A09.csv | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| docs/ARCHITECTURE_FOUR_LAYER_CONSTITUTION.md | COPY_REFERENCE_DOCUMENT | Copied unchanged into docs/; local ARCHITECTURE_DECISIONS.md reconciles terminology and runtime facts. |
| docs/ARGUE_AGAINST_MYSELF.md | COPY_REFERENCE_DOCUMENT | Copied unchanged into docs/; local ARCHITECTURE_DECISIONS.md reconciles terminology and runtime facts. |
| docs/EXECUTION_STAGES_AND_ACCEPTANCE.md | COPY_REFERENCE_DOCUMENT | Copied unchanged into docs/; local ARCHITECTURE_DECISIONS.md reconciles terminology and runtime facts. |
| docs/NEXT_ACTION.md | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| docs/OWP_OPEN_WORLD_WEALTH_SPEC.md | COPY_REFERENCE_DOCUMENT | Copied unchanged into docs/; local ARCHITECTURE_DECISIONS.md reconciles terminology and runtime facts. |
| docs/SECURITY_AND_RELIABILITY_GATES.md | COPY_REFERENCE_DOCUMENT | Copied unchanged into docs/; local ARCHITECTURE_DECISIONS.md reconciles terminology and runtime facts. |
| docs/SOURCES_AND_RATIONALE.md | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| docs/TRACEABILITY_0_TO_18.csv | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| examples/EXAMPLE_OFFLINE_COMMANDS.md | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| prompts/FOUNDER_MASTER_DIRECTIVE_FOR_CODEX.md | ARCHIVE_DIRECTIVE | Read full; preserved as REVIEW_KIT_FOUNDER_DIRECTIVE.md; nonexistent prototype/apex_reference path corrected in decisions. |
| pyproject.toml | REVIEW_REFERENCE_ONLY | Read full; keep existing project settings/instructions/trace registry; no automatic package installation or runtime activation. |
| reference/OPUS_IMPLEMENTATION_BRIEF_ARCHIVE.md | HASH_MATCH_EXISTING_ARCHIVE | Byte-identical source already read; retain current original and cached full review. |
| reference/ORIGINAL_ACCEPTANCE_GATE_FA.md | HASH_MATCH_EXISTING_ARCHIVE | Byte-identical source already read; retain current original and cached full review. |
| reference/ORIGINAL_ACCEPTANCE_MATRIX.csv | HASH_MATCH_EXISTING_ARCHIVE | Byte-identical source already read; retain current original and cached full review. |
| reference/ORIGINAL_DOCUMENT_HASHES.txt | HASH_MATCH_EXISTING_ARCHIVE | Byte-identical source already read; retain current original and cached full review. |
| reference/ORIGINAL_MASTER_MANIFESTO_READONLY.md | HASH_MATCH_EXISTING_ARCHIVE | Byte-identical source already read; retain current original and cached full review. |
| reference/ORIGINAL_USER_SOURCE.md | HASH_MATCH_EXISTING_ARCHIVE | Byte-identical source already read; retain current original and cached full review. |
| reports/BUILD_AUDIT_REPORT.md | HISTORICAL_EVIDENCE | Read full; historical 69 tests/status superseded by local rerun; no field claim. |
| reports/LOCAL_STATUS.json | HISTORICAL_EVIDENCE | Read full; historical 69 tests/status superseded by local rerun; no field claim. |
| reports/UNIT_TEST_LOG.txt | HISTORICAL_EVIDENCE | Read full; historical 69 tests/status superseded by local rerun; no field claim. |
| tests/test_epoch.py | RUN_REFERENCE_ONLY | 69 supplied tests reproduced; adapt stricter tests to current suite, no wholesale import. |

## Integration contract

Existing domains opportunity/studio/personal remain unchanged. Reference research/career/creative/system domains are not silently mapped into current policy. Existing runtime/kernel.sqlite3 and event schema remain unchanged; no competing database is introduced and no migration runs. Current atomic workflow journal, readonly reader, per-case lab receipts, domain ranking and studio exports remain in place.

OWP adaptation is preparation/coverage only: finite list inputs, strict zero integer budget, full-input validation before truncation, structured digest IDs, declared omitted scope and no connector activation. Coverage reads a bounded local snapshot and checks hashes/IDs; declared inspection does not establish market coverage, independent review or customer demand. Existing opportunity economics/ranking remains the value assessment module.

Future imports require fixes plus concurrency/failure tests, actual identity/authority enforcement, migration/recovery design and independent review. Do not enable the reference worker as a shortcut.
