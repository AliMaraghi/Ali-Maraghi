# RDE architecture and adversarial decision record

Status: first local engineering increment, 2026-11-09. No production acceptance.

## Strongest objections first

1. An evidence ledger can organize incorrect claims perfectly. A URL, source
   label, matching quotation and content hash do not establish authenticity,
   causal validity, claim entailment or customer demand. Human/source review is
   still required, and this version never marks a claim true.
2. A collection of model critics can share the same mistakes. The shipped critic
   is a deterministic checklist. It is independent code from candidate input,
   not an independent empirical reviewer. Lexical hypothesis diversity is weak;
   semantic distinctness and negative-space usefulness remain untested.
3. A Python policy module is not a security sandbox. The CLI has no external
   adapters; arbitrary same-user Python/code/database access is outside its
   protection. Production would require separate identities, isolated processes,
   resource caps and OS/network enforcement, followed by staged security tests.
4. Zero paid API spend does not mean zero cost. Founder review time, maintenance,
   compute and hosting are costs; their incremental amounts are unmeasured.
   Building all domains before measuring one useful outcome would be wasteful.
5. SQLite plus hash chaining is local persistence, not encrypted personal memory,
   off-site backup, protection against full-chain rewriting, or high availability.
   A lost or compromised development host remains a single failure point.
6. Synthetic checker improvements are not improved intelligence. Historical
   training overlap cannot be proven absent. Once the frozen fixtures have been
   inspected/run, later versions must treat them as regression cases and create
   fresh independently controlled evaluation cases.

## Choice and simpler alternatives

Use one bounded Python workflow and standard-library SQLite. Keep the existing
service separate; add no agent service, queue, paid model, vector database or
account connector for this increment. Preserve the original proposed stack as
future scope with dependencies in REQUIREMENTS.json.

| Alternative | Suitable baseline task | Current evidence / decision |
|---|---|---|
| Manual evidence checklist | Review identical source packet, claims and alternatives with fixed time allowance | Human usefulness/time baseline NOT RUN; must be measured before claiming advantage |
| Conventional Python automation | Enforce exact policy rules and keep structured records | Full standalone policy checklist matches 24/24 synthetic cases; retain ordinary code for this function |
| ChatGPT, Claude or Codex used directly | Same public packet, problem and output rubric; fixed time/access allowance | No comparative model runs or product superiority claims; no paid API invoked |
| Multi-agent architecture | Same task plus added coordination/review cost | No measured advantage; defer runtime agent proliferation |
| Current local kernel | Persistent evidence/decision history with structural checks | Offline safety, persistence and traceability demonstrated; real decision quality NOT TESTED |

The weak two-condition baseline scores 13/24; the explicit policy scores 24/24.
The complete conventional checklist also scores 24/24. These fixtures support
explicit deterministic controls, not an APEX advantage over a proper script or
any language model. One sub-millisecond timing run is not a performance result.

## Executable boundaries

`schema.py` accepts strict, bounded case records: problem, assumptions, baseline,
at least two candidate mechanisms/predictions/falsifiers, claims, evidence and
negative-space questions. Unknown fields, duplicate JSON keys/identifiers,
nonfinite values and unsupported private sensitivity labels fail closed.

`evidence.py` reads bounded regular artifacts inside the workspace through
no-follow directory descriptors. It checks SHA-256, exact excerpt presence,
source URI syntax, observation time, expiry, domain and synthetic/model labels.
No remote URL is fetched. The author/rights/authenticity of an artifact still
requires review; falsely labelling private data public is not solved by a label.

`critic.py` flags unsupported/misattributed references, refutation, duplicate
source content/hosts, model agreement, stale sources and lexical duplicate
alternatives. It preserves contradictions. It cannot prove semantic independence,
authenticity, completeness or legal correctness.

`engine.py` produces one review decision, input/code fingerprints, claims and
provenance, hypotheses, open objections and a proposed smallest experiment.
Candidates are operator supplied. Autonomous problem/hypothesis generation and
live negative-space research remain NOT IMPLEMENTED; the former static RDE is
retained for compatibility, not renamed as a functioning intelligence engine.

`policy.py` authorizes only a zero-cost local decision record. Cost uses integer
pence; bool, float, negative, unknown and positive amounts fail. No arbitrary
callback, shell, SQL, URL fetch, message, publication or payment is dispatchable.
FREEZE_INGRESS/STOP_EXECUTION deny new records. DISABLE_EGRESS and
REVOKE_CREDENTIALS leave local records available while external actions remain
denied. Actual worker shutdown and provider token revocation are not implemented.

`memory.py` stores transactional append-only events, idempotency conflicts,
domain-filtered reads and a hash chain. A decision survives CLI process restart.
`lab.py` evaluates labelled cases twice, detects declared ID/content leakage,
counts correctness/safety failures and records timing. Local version promotion
requires measured improvement against the CURRENT champion and consistent
metrics; failed candidates remain recorded. Rollback can select only a previously
promoted local version or baseline. These are experiment pointers, not deployed
code rollouts. Receipts and Python calls are trusted operator inputs, not model
output authentication. Canary/deployment/policy evolution is absent.

## Domain increment

- Opportunity: Decimal interval arithmetic for explicitly assumed probability,
  conditional revenue, cash and time cost. No estimate of real demand, eligibility,
  tax or realized income. Smallest experiment and assumptions are retained.
- Studio: a 75-second Lagos, Portugal timeline, original proposed narration,
  shot/sound/edit plan and rights/intake/QC requirements. Missing authorized media
  gives BLOCKED. No renderer or completed film; style approval is pending.
- Personal: a bounded priority/time planner with low-energy preference. Withdrawn
  or absent contact consent blocks contact planning; allowed contact stays draft.
  No account access, mind reading, health diagnosis or outcome guarantee.

## Reproduce locally

Run from `/home/apexdev/apex-work`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py
python3 -B scripts/traceability.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmark_kernel.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/run_examples.py all
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=core python3 -B -m apex.kernel.cli review examples/evidence_review_synthetic.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=core python3 -B -m apex.kernel.cli review examples/evidence_review_synthetic.json --record --key my-review-1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=core python3 -B -m apex.kernel.cli history --domain opportunity
```

Review exit 2 means blocked/invalid; a synthetic fixture is intentionally blocked.
Exit 0 means ready for human review, never empirical verification. Recording a
blocked result is useful failure memory. Reuse a key only for an identical
evaluation; changed source/code/freshness needs a new key. The runtime database
is deliberately excluded from Git and contains only local public/synthetic data.
