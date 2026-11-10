# APEX Epoch — Four-Layer Architectural Restoration and Crosswalk

**Status:** engineering proposal and partially coded OFFLINE reference; **NOT deployed**; **NOT Apex 4.4 completed**. Source: `reference/ORIGINAL_MASTER_MANIFESTO_READONLY.md`, dated 8 Nov 2026. The current available source records six operational sublayers under §5; the founder also recalled an earlier *four-layer* presentation. The four MACRO layers below are an explicit restoration/synthesis of the architectonic intent, **not a false claim to recover the exact wording of an unavailable older message**.

## One constitutional core / four macro layers / six §5 operational sublayers / eighteen specialist slots

```
               Founder mandate: original 0–18, immutable canonical documents
               Constitutional Kernel  |  Owner Authority  |  Source Provenance
                                         |
+--------------------------------------------------------------------------------+
| LAYER I  OPEN WORLD + KNOWLEDGE                                                  |
| Lawful global search | Source Discovery | OWP/OWOE | Weak Signals | Ingestion    |
| Source manifests | Evidence provenance | data minimisation | lawful connectors |
+--------------------------------------------------------------------------------+
                                         |
+--------------------------------------------------------------------------------+
| LAYER II  COGNITION + RECURSIVE DISCOVERY                                        |
| Cognitive Planner | UAC | evidence graph | hypothesis generator | independent    |
| critic | causal alternatives | negative-space inquiry | Decision Twin         |
+--------------------------------------------------------------------------------+
                                         |
+--------------------------------------------------------------------------------+
| LAYER III ACTION + VALUE PRODUCTION                                             |
| Typed tools | capability firewall | deterministic Action Gateway | n8n orchestration|
| Redis workers | domain products: OWP, media, CFO, social, corporate, etc.         |
+--------------------------------------------------------------------------------+
                                         |
+--------------------------------------------------------------------------------+
| LAYER IV ENDURING MEMORY + EVALUATION + COMMAND                                 |
| PostgreSQL/pgvector | audit | evolutionary experiments | rollback | zero-spend  |
| budgets | personal data segregation | recovery | private iPhone command plane   |
+--------------------------------------------------------------------------------+
      All layers subject to cross-cutting least privilege, owner consent, 4-stage kill switch
```

## Architectural invariant: four is NOT one

Do not collapse Layers I–IV into a single RDE class or a single generic LLM chain. A single coherent system means *shared contracts, constitutional controls, provenance and monitoring*, NOT one enormous process with all privileges. Physical process/module count can vary; logical boundaries cannot silently disappear. RDE belongs in Layer II; it consumes Layer I evidence, submits proposals to Layer III gateway, and receives Layer IV evaluation feedback. No layer's component can issue itself new powers.

## Six operational sublayers retained verbatim by reference

| §5 sublayer in archived source | Four-layer implementation crosswalk | Acceptance requirement |
|---|---|---|
| 5-1 Sources | Layer I | provenance, source access, license, freshness and independence |
| 5-2 Memory and knowledge | Layers I & IV | vector/graph retrieval with domain isolation and deletion rights |
| 5-3 Planning | Layer II | DAG decomposition, cost/time constraints, uncertainty |
| 5-4 Multiagent production | Layers II & III | UAC, typed tasks, minimal agent selection and verification |
| 5-5 Audit and security | Cross-layer, Layers III & IV | Policy Engine, zero-trust data, gateway and egress checks |
| 5-6 Publication and feedback | Layers III & IV | permitted publication, return metrics, no unapproved posting |

The early `0.167.0` Codex workflow is **development tooling**, not the full Apex runtime. APEX must continue independently of the founder's laptop and Codex after deployment (with realistic single-VPS availability limitations).

## Chapter-by-chapter preservation ledger

No numbered chapter of 0–18 is removed. 0: independent ownership, cost, credential boundary, backup, kill switch. 1: open source discovery, evidence and global monitoring. 2: founder identity and Voice DNA with stated/observed/inferred provenance. 3: publishing across LinkedIn, YouTube, Instagram, X, TikTok and permitted channels. 4: Ali original legacy, timeless thesis + current evidence. 5: unified planner, UAC, Evidence Graph and Action Gateway. 6: consent-based Social/Relational Intelligence and professional monitoring with separated company/personal contexts. 7: **OWP/Open-World Wealth Discovery** and economic capture. 8: eighteen specialist **slots** with individual implementation gates. 9: UK Personal CFO, entitlements, mortgage, tax and dated jurisdiction. 10: budgets, trust, metrics and failure accounting. 11: legal rights, information privacy, key custody. 12: encrypted personal dossier with audit trail. 13: agentic autonomy, decision rights and Decision Twin. 14: independent strategic foresight and weak signals. 15: queued operations and time zones. 16: scale, creative influence and audience economics. 17: controlled self-evolution with held-out evidence and rollback. 18: film/audio end-to-end asset registry and export QC.

All appendices in the archived master source remain binding. `A01`–`A09` are separate cross-domain outcome gates; passing a module unit test does not mean passing an A0x gate.

## Interfaces and data contracts

Every task must carry `task_id`, source and domain scopes, budget cap, deadline, data classification, creator, decision rights and idempotency key. Every specialist response must carry all fields of the Universal Agent Contract: `agent_id`, `role_version`, `task_id`, input/output schemas, `capabilities`, `allowed_domains`, evidence refs, claims, uncertainties, risks, confidence calculation method, estimated cost, status and next actions.

No model output can grant action authority; the Action Gateway resolves capabilities from a separately governed store, verifies scoped human approval and records consumed approvals exactly once. RDE outputs are *proposals*, never direct external writes. RSS/web/third-party model text is untrusted data.

## Data residency and isolation

- **Corporate / AMD environment:** no corporate mail, trade secrets, documents, identities or access tokens brought into a personal Apex VPS without explicit legal organisational permission and security review. Even work-related news can come from *public sources* only.
- **Health, benefits, finance, housing, legal, sexual/relationship data:** no raw ingestion in the unencrypted offline reference. Production requires separate encrypted store, scoped consent, expiry, revocation, access logs and deletion policy.
- **Public media and research:** only citations to independently checked factual evidence. No automatic spreading of private facts to publishing agents.
- **Customer or social platform activity:** consent, rate limits, terms of service and owner approval.

## Production platform target (NOT installed by this ZIP)

1. Ubuntu VPS hardening, named non-root system accounts, key-based access, firewall and patch/recovery policy.
2. Separate staging from live with Git-integrated tested deploys, secrets outside repository, image digest pinning and migrations.
3. PostgreSQL/pgvector migrations, column-level protection and audit; Redis `noeviction`, dead letter and persistence policy; n8n main + queue-mode workers as appropriate, with version + verified digest. `n8n` is an orchestrator, NOT the reasoning brain.
4. Python core and job/execution APIs; integration-specific worker containers; read-only metrics, health, logs and alerting.
5. Private iPhone web application behind authenticated TLS/tailnet or equivalent and per-action approval screen. Must protect lock-screen previews, caches and private dossiers.
6. Backups off-VPS encrypted with independently tested restore; rollback with evidence, canary release and consent gates.
7. Business continuity: a single VPS is a single point of failure; do not claim 100% uptime. Define SLO and incident response before high-stakes automation.

## Cross-layer state machine and guarantees

`DISCOVERED -> SOURCED -> REVIEWED -> PROPOSED -> EXPERIMENT_PREREGISTERED -> TESTED -> OWNER_APPROVAL -> DEPLOYED -> OBSERVED_OUTCOME -> RETAIN/ROLLBACK`.

Reject transitions lacking upstream evidence. `TESTED` means test execution; it never implies positive real-world outcome. Minimum risk protections: bounded queues, at-least-once workers with idempotent handlers, strict budget reservation, structured logs, dead-letter handling, checksum verification and explicit owner kill stages. Honest `BLOCKED` status is a successful safety outcome, not proof of capability.

## What is actually coded in this package

Offline Python contracts and demonstrations: conservative URL validation (not full SSRF-proof fetcher), local source registry, event hash chain, public research evidence, bounded search probes, deterministic hypothesis-test proposal generator, OWP scenario sensitivity, zero-spend ledger, permit/deny gateway, human approval record, bounded queue and lease, paired evaluation, signature film preproduction and source integrity controls. External data acquisition, LLM integration, video rendering, production encryption, n8n/Redis deployment, secure iPhone PWA and long-running production workers are **not implemented**.

## Adversarial review: why four layers can still fail

- Architectural elegance is not customer willingness-to-pay or user benefit.
- Four logical planes can become four different silos unless domain schemas are stable and tested end to end.
- Shared evidence can produce common-mode errors; publisher labels are not proven independence.
- One VPS can suffer crashes, exhausted disk, unexpected bills, weak SSH or an unavailable upstream provider.
- Automated benchmark tuning can overfit the test cases; withheld, independent, time-shifted cases are required.
- An uncontrolled model may pursue proxy metrics: many papers, many followers, many agents, many lines of code, all without value.
- Formal correctness of gateways can be undermined by alternate tool access; production must sandbox tools and use egress controls.

**Outcome gate:** 19 numbered headings + appendices preserved; 9 acceptance contracts maintained; code per capability only promoted by reproduced domain tests and founder-authorised deployment.
