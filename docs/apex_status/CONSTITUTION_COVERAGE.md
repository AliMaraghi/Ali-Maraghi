# APEX 4.4 constitution coverage — first engineering increment

This is a derived, private development record. The original manifesto, archive,
mission contract, acceptance gate and original CSV remain immutable. The master
SHA-256 is `3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd`.

`REQUIREMENTS.json` records 178 separately addressable requirement groups/clauses
and 968 nonblank source-line units across all five authoritative inputs. Each unit
has a source path, one-based line range, raw-byte SHA-256 and requirement links.
Blank lines alone are excluded. Headings, framing, archive text, table rows and
source gaps are retained; no heuristic discards less prominent requirements.
The registry references sensitive archive text without copying it into this report.

This establishes **source retention and navigable scope**, not complete atomic
semantic decomposition or fulfilled requirements. A paragraph may contain several
obligations. Its exact source text remains authoritative; acceptance requires all
those obligations, not just the English summary. Independent semantic review of
the decomposition remains outstanding. No requirement has full acceptance PASS.

## Reproduce and interpret the gate

```sh
python3 -B scripts/traceability.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=core python3 -B -m unittest discover -s tests -p test_traceability.py -v
```

`PASS_SOURCE_TRACE_ONLY` means the source hashes, line retention and required IDs
match. It does not mean G1 semantic coverage or any product domain has passed.
The tests deliberately remove requirements, alter source/line hashes, forge
completion/deployment and attempt invalid mappings. They are offline engineering
tests, not independent validation of intelligence or commercial value.

The generator's `--build` option creates a missing registry only. It refuses to
overwrite existing reviewed status. Later sessions may update implementation,
test, evidence and status fields, but must keep original source anchors and units.
`implementation_status` uses the mission vocabulary; `acceptance_status` uses the
acceptance gate vocabulary. They are different axes. Local prototype tests cannot
be translated into DEPLOYED or full acceptance PASS. This registry version rejects
such claims until an independently reviewed acceptance-evidence process exists.

## Section-to-code and future acceptance matrix

Paths below are tested prototype foundations, not full implementations. The JSON
records their relationship explicitly and links bounded tests and evidence.
Mapped foundations are PROTOTYPE/PARTIAL; remaining requirements are NOT_STARTED /
NOT TESTED. No full section has acceptance PASS. The registry contains dependencies
and future acceptance scenarios for every row.

| ID / section | Requirement retained | Candidate foundation | Missing prerequisite / acceptance evidence |
|---|---|---|---|
| S00 / 0 | Ownership, infrastructure, budgets, four stop stages, recovery | `core/apex/kernel/policy.py`, `memory.py` | Isolated staging, least privilege, restore drill, explicit deployment authority |
| S01 / 1 | Open research, provenance, source discovery, weak signals | `core/apex/rss.py`, `kernel/evidence.py` | Multiple actual sources, false-alert evaluation and independent source review |
| S02 / 2 | Identity, style, stated/observed/inferred memory, energy | None | Consented memory, approved style samples, correction/deletion, blinded grading |
| S03 / 3 | Platform-specific publication and audience objectives | None | Official capability access, rights, publication consent and actual analytics |
| S04 / 4 | Original signature, timeless thesis, evidence, legacy | `core/apex/domains.py` | Owner style approval and independent originality/audiovisual review |
| S05 / 5 | Planner, contracts, evidence graph, untrusted data, gateway | `core/apex/kernel/` | Full planner/DAG contracts and independent semantic/evidence validation |
| S06 / 6 | Respectful social support and permitted professional work | `core/apex/domains.py`, `kernel/policy.py` | Domain consent, private storage and official account capabilities |
| S07 / 7 | Open opportunity discovery, economics, disconfirmation | `core/apex/domains.py`, `kernel/engine.py` | Ten real opportunities, three independent checks, actual outcome evidence |
| S08 / 8 | Eighteen specialist functions and boundaries | None | Callable role contracts, positive/negative capability tests; source gaps retained |
| S09 / 9 | Personal finance, benefits, tax, housing | None | Dated official rules, qualified calculation checks and domain consent |
| S10 / 10 | Costs, failures, trust, quality metrics, red team | `core/apex/kernel/policy.py` | Full hierarchy, invoice reconciliation, retry controls and recovery evidence |
| S11 / 11 | Privacy, lawful purpose, rights, employer separation | `core/apex/kernel/policy.py` | Purpose/retention/access lifecycle and appropriate legal review |
| S12 / 12 | Isolated dossier, independent keys and audit | None | Encrypted storage, key management, consent and deletion/access tests |
| S13 / 13 | Autonomy, Decision Twin, revocation, low-energy mode | `core/apex/kernel/policy.py` | Explicit grants, learned preferences, expiry and manageable approval UX |
| S14 / 14 | Foresight, threat-to-opportunity, missed opportunities | `core/apex/kernel/engine.py` | Independent time-stamped cases and outcomes |
| S15 / 15 | Publication state machine, queues, London timezone | None | Official access, DST/idempotency/retry tests and actual receipts |
| S16 / 16 | Global growth, language mix, cultural/economic scenarios | None | Actual audience observations and measured commercial outcomes |
| S17 / 17 | Controlled evolution, holdout, canary, rollback | `core/apex/kernel/memory.py` | Independently controlled evaluation and promotion evidence |
| S18 / 18 | Complete real film and audio production | `core/apex/domains.py` | Authorized Lagos/Portugal media, audio, renderer, playable film and review |

All eighteen roles have independent `CLAUSE-8-1` through `CLAUSE-8-18` entries.
Social requirements have `CLAUSE-6-1-1` through `CLAUSE-6-1-20` entries, with
later clauses linked to their surviving archived source. Numbered infrastructure
and cognitive clauses and all seven health clauses also have independent records.
The registry contains exact authoritative source locations; the source itself is
the full requirement wording.

The registry also retains 47 individually numbered historical clauses as
`ARCHIVED-*` records and all seven engine stages as `RDE-*` records. Historical
clauses retain precedence notes; operational formulas, vendor names and old
permissions are not silently treated as current validated facts.

## Appendices and retained future domains

| Registry ID | Retained scope | Dependency and acceptance scenario |
|---|---|---|
| APP-HEALTH; HEALTH-1..7 | Health, longevity, skin, exercise, ergonomics and recovery | Consented isolated data; human evidence appraisal, uncertainty and safe escalation; no treatment claims |
| APP-KERNEL | Constitutional kernel and domain reasoning boundaries | Authority/claim-type separation and domain controls |
| APP-PWA | Secure iPhone command centre | Authentication, authorization, session revocation, private cache/notifications and low-energy view |
| APP-ML | Real datasets, learning and prediction | Versioned real labels, disjoint evaluation, drift/calibration/fairness and rollback |
| APP-ORIGINALITY | Original cultural work and ownership | Approved style, rights and human originality review |
| APP-PRESERVATION | Non-deletion and source precedence | Hashes, traceability, conflicts and honest source gaps |
| APP-ACCEPTANCE | A01-A09 and G0-G7 | Independent evidence for every mission and gate; no compensating aggregate score |
| APP-BLOCKERS | Honest status and actionable alternatives | Observable blockers, permitted next action and actual cost records |
| APP-SIGNATURE | Approval/authorship limits | No fabricated legal approval or digital signature |
| APP-ARCHIVE; SOURCE-ARCHIVE | Historical source preserved | Byte preservation and explicit precedence, without reproducing private content |
| APP-ARCHIVED-GATE; ACCEPTANCE-CONTRACT | Complete retained acceptance contract | Exact scenarios, evidence requirements, failures and untested states |
| MISSION; ACCEPTANCE-MATRIX | Session programme and original acceptance CSV | Bounded implementation and dated continue/pivot/stop; original CSV unchanged |

## Acceptance state

Each of A01-A09 and G0-G7 has its own entry. None is promoted to full PASS by this
registry. The initial complete-system verdict remains **NOT ACCEPTED**: an offline
increment cannot establish all critical domains, deployment or independent value.
Specific prototype test evidence belongs in the execution report and can support
PARTIAL, with its limits, without rewriting the frozen original matrix.

## Source gaps and conflicts

1. Historical 8-1..14 wording is incomplete. The canonical role assignments are
   proposed operational completion, explicitly identified as such. Each role
   carries SOURCE GAP; it is not a recovered quotation.
2. Historical 12-1..10 and 18-3..6 survive as grouped summaries. Separate
   `HISTORICAL-12-*` and `HISTORICAL-18-*` records retain the missing clauses and
   dependencies without inventing their individual wording. Canonical current
   requirements can still be engineered; historical completeness stays unresolved.
3. Historical assistive/manual-only action language differs from later permitted
   autonomy. Implement the canonical scoped, revocable authorization model and
   the current user's stricter no-external-action/no-spend boundary. Retain the old
   text; do not interpret it as authority to connect accounts or act externally.
4. Historical fixed GMT times are superseded for implementation by canonical
   `Europe/London` with daylight-saving handling. Time slots remain hypotheses.
5. Historical model/vendor/version/price names and numerical growth or income
   targets are preserved as source statements. They are not verified current
   products, prices or achieved outcomes and must not be hardcoded as facts.
6. Some historical phrases claim complete recovery, production readiness or
   extraordinary performance. Canonical honesty notes and the mission contract
   explicitly reject treating those phrases as evidence of implementation.
7. The gate prose says seven gates in one place but explicitly enumerates G0-G7.
   All eight enumerated gates are retained; no gate is dropped to fit the count.
8. The programme runs from 9 to 30 November 2026: 21 elapsed days, 22 inclusive
   calendar dates. Treat 9 November as baseline day 0 and 30 November as day 21;
   do not imply that future validation has already occurred.

Next acceptance work: independently review semantic decomposition, attach actual
bounded code/test/evidence links after execution, then collect real observations
and owner/independent reviewer feedback. Full domain acceptance remains separate
from the source-preservation and local software tests.
