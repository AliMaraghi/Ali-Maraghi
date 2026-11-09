# Verified development reality

Verification date: 2026-11-09, Europe/London. Workspace: `/home/apexdev/apex-work`.
Scope: unprivileged local development, never production/service verification.

## Environment and original state

The earlier conversation failed before shell startup with `bwrap: loopback:
Failed RTM_NEWADDR: Operation not permitted`. No bypass was used. On resume,
sandboxed `pwd` succeeded. Python 3.12.3 is installed; UID observed was 1000.
No Git repository initially existed. Local-only commit `61adae7` preserves all
39 original files; no remote was added. Workspace and separately protected `.git`
write access were obtained through narrowly scoped permission grants.

The prior Codex report recorded no changes/tests because of the sandbox failure.
It remains at `61adae7:reports/codex/first_run_report.md`. The RDE ZIP has nine
entries; all five implementation/script/test patch files matched working copies.
Its embedded manifesto matched the canonical digest. The previous RDE was a
static checklist with hardcoded failed empirical gates, no persistent memory and
no executable action gateway. Its claims were appropriately conservative.

The five authoritative inputs were read in full, including sections 0–18,
appendices and historical text. All 14 packaged SHA256SUMS entries were checked
before and after development. Manifesto SHA-256 remains:

`3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd`

Audit included existing Python/tests/scripts, Dockerfile, Compose, READMEs,
connection decisions, previous report and RDE archive contents. No Docker,
backup, monitor or service script was executed. Archived uptime and 16-ingested-
item claims were not reproduced and remain historical reports.

## Reproduced evidence

| Check | Result | Evidence |
|---|---|---|
| Original RDE tests | 10 passed | `legacy_baseline.txt` |
| Original pytest command | Unavailable: package absent | `legacy_baseline.txt` |
| First combined runner | 92 passed, 2 skipped, 1 child-import-path failure | `reports/validation/offline_tests_initial_failure.txt` |
| Final offline suite | 96 passed, 2 skipped, no failures/errors; 98 total | `reports/validation/offline_tests.txt` |
| Frozen policy fixtures | Kernel24/24; weak rule13/24; conventional checklist24/24 | `reports/validation/policy_benchmark.json` |
| Evidence adversarial cases | Eight synthetic corruption/conflict/source cases exercised | `tests/test_kernel_holdout.py`, offline test report |
| CLI process restart/repeat | Exactly one record per key; verified journal; no studio records | `reports/validation/cli_smoke.json` |
| Source trace | 178 entries, 968 nonblank source units, matching hashes | `reports/validation/traceability.json` |
| Domain examples | Assumed net -GBP50 to GBP75; 30-minute plan; 75-second film BLOCKED by seven assets | `reports/validation/domain_examples.json` |
| Static checks | 31 Python files parse; three shell scripts pass syntax check; clean diff whitespace | Commands below |

Two original FastAPI TestClient tests are skipped. FastAPI, httpx, pytest, psycopg
and uvicorn are absent. No dependencies were installed. Mocked route/DB/network
tests establish local contracts, not live integration. A complete conventional
policy checklist matches the candidate; no intelligence advantage is established.
Single-session sub-millisecond timings do not support performance claims.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py
python3 -B scripts/traceability.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmark_kernel.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/run_examples.py all
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/smoke_kernel.py
sha256sum -c docs/apex_handoff_20261109/SHA256SUMS.txt
bash -n scripts/backup_postgres.sh scripts/run_discovery_once.sh scripts/verify.sh
git diff --check
```

Opportunity figures are fixture assumptions, not projected/realized user income.
No measured productivity gain, verified demand, independent model comparison,
approved artistic style or completed film exists. No public-source retrieval or
fresh external verification ran; the real-source research report remains pending.

## Remaining acceptance work and costs

Autonomous hypothesis generation, semantic verification, open-world search,
independent real evaluations, encrypted personal memory, global stop/revocation,
canaries, authenticated PWA/queues and integrations remain incomplete. Source
retention is not complete atomic semantic decomposition. Full APEX acceptance
remains NOT ACCEPTED; this is a tested local prototype foundation.

Additional paid API spend GBP0/USD0; external calls0. Included coding-agent use is
distinct from paid third-party APIs. Hosting, compute and human time are not
separately metered. Reviewers hit their usage limit after saving partial work;
parent inspected/repaired and reran it. No credits or paid service were purchased.
