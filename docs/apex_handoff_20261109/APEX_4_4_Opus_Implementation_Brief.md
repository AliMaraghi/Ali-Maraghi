# APEX INTELLIGENCE CORE — CLAUDE OPUS MASTER IMPLEMENTATION BRIEF

**Document type:** Markdown (`.md`) — engineering instructions for Claude Opus / Claude Code  
**Project:** Apex Intelligence Core v4.4  
**Date:** 2026-11-06  
**Status:** Design and implementation brief; not executable software by itself.

## IMPORTANT: INPUT INTEGRITY & SOURCE-OF-TRUTH

Two separate documents are provided:

1. `APEX_4_4_Opus_Implementation_Brief.md` (this file): the task instructions, validation and execution plan.
2. `APEX_4_4_User_Supplied_Source.md`: a preserved working transcription of the user's latest Apex v4.4 text. Treat this as an immutable input to be checked against the user's original source. The source text itself may contain pre-existing omissions, substitutions, contradictions and accidental pastes; **do not silently correct or erase any of these**.

If an earlier, longer original manifesto is available, treat it as **SOURCE_ORIGINAL** and the latest supplied text as **SOURCE_REVISION**. Archive both first, then perform a line-level comparison and merge by explicit, traceable additions only. Do not claim byte-for-byte identity with the earlier manifesto unless checked against the actual original file or a verifiable hash.

## PRIMARY USER DIRECTIVE

The user wants an extraordinarily capable, adaptive, global, system-level personal intelligence architecture with strong strategic reasoning, memory, decision support, multimodal publication, financial and business opportunity discovery, and genuinely useful social and relational intelligence. They demand no silent abridgement, no undeclared omissions and no replacement of their core objectives with the assistant's preferences.

**Preserve the full section structure 0–18, every numbered subsection and every appendix.** Preserve original passages verbatim in an immutable archival file. Build a separate, integrated deployment version with documented amendments and a complete change ledger. Never represent a summary or excerpt as a complete manuscript.

Preserve user-defined scope, including private consensual adult relationships and nightlife discovery, as its own data-isolated domain. Do not automatically import those preferences into professional, financial or public communications. Natural, context-aware, distinctive writing is required; do not fabricate first-person experiences, identities or affiliations. Distinguish lawful, permissioned automation from unsupported platform capabilities. Do not build covert sensitive-trait profiling, nonconsensual emotional manipulation or automated unsolicited bulk outreach.

## ACCEPTED ENGINEERING CHANGES — INTEGRATE IN PLACE, DO NOT RESTRUCTURE

- Section 0: verified official n8n image and digest-pinning, PostgreSQL/Redis queue compatibility, staged migrations and rollback, OAuth exact redirect URIs, reverse-proxy configuration, four-stage kill switch, secrets held in a separate credential control plane, dynamic vendor-pricing registry and budget ceilings.
- Section 1: dynamic source discovery, academic and commercial source-quality hierarchy; ensure unknowns and contested research are not presented as certain.
- Section 2: observed/stated/inferred identity and contextual information; feedback and reflection loop with versioning.
- Section 3: retain all original platforms, posting goals and ambitions; classify targets as unverified scenarios rather than guaranteed outcomes.
- Section 4: global relevance; timeless thesis plus current evidence; safeguard independent thought and domain separation.
- Section 5: provenance and claim-level evidence graph; untrusted external content is DATA rather than AUTHORITY; universal typed subagent contract; independent deterministic Action Gateway; genuine fact-checking and audit.
- Section 6: **replace only the rejected 'assistive-only' social proposal** with the author's autonomous, context-sensitive social architecture. Retain existing professional-intelligence section 6-2. Include the requested adult social, nightlife, consensual intimate experience discovery and community engagement extensions (6-1-15 through 6-1-20). Allow standing authorisation for actions which are actually supported and permitted. Platform capability=UNSUPPORTED where no official access exists. Preserve consent, truthful identity and per-domain privacy. The user's earlier source contains several inconsistent or accidentally pasted 6-1 passages; identify them in the change ledger rather than pretending they form a clean specification.
- Section 7: open-world lawful wealth discovery without arbitrary limits on geographical, sectoral or opportunity search; broad exploration, permissioned consequential execution; anti-confirmation-bias review; dynamic opportunity portfolio.
- Section 8: universal schema for every agent, role and scope boundaries; model routing. Do not claim to have seen detailed prompts for 8-1 to 8-14 where only their titles were provided: mark the missing definitions and author proposed implementations in a separately identified additions section. Validate 8-15 through 8-18.
- Section 9: deterministic finance and benefits models based on current jurisdiction and primary sources; separate means-tested UC from non-means-tested PIP; account for the nature of a dedicated care direct-payment account; financial scenarios rather than automatic ESPP sale; lender-specific mortgage affordability, not guaranteed 4.5x salary.
- Section 10: model actual provider billable units and dynamic prices; budgets and retry bounds; meaningful KPIs, SLOs, cost and incident controls.
- Section 11: UK GDPR, Data Protection Act 2018, Data (Use and Access) Act 2025, retention by purpose, rights and appropriate governance; organisational confidentiality.
- Section 12: encrypted and isolated personal dossier with key management, scoped access, audit and retention; no leakage into unrelated domains.
- Section 13: decision twin = decision support, not policy authority; capability control outside the model; reliable audit and fatigue controls.
- Section 14: preserve all original future-facing opportunities and connect to the open-world discovery loop.
- Section 15: provider-supported multi-platform posting; Europe/London DST-aware scheduling; no hard-coded year-round GMT assumption.
- Section 16: retain original strategic audience goals and revenue ambitions as scenarios, with measurable conversion and retention KPIs.
- Section 17: sandbox → evaluation → canary → audited promotion for self-improvement; structural changes require explicit approval.
- Section 18: preserve video and voice objectives; provider-neutral current-model registry, validated schema, costs per provider's actual billable unit, original/licensed content, explicit approval for any voice cloning and privacy controls.
- Appendices: full original appendices preserved; Constitutional Kernel, Domain Temperature Isolation, Capability Manifest, source registry, test cases, recovery playbook and immutable change audit appended or integrated transparently.

## CLAUDE OPUS OPERATING DIRECTIVE (COPY INTO PROJECT INSTRUCTIONS)

You are the lead systems architect and implementation engineer for Apex Intelligence Core v4.4. Your task is to deliver a COMPLETE, TRACEABLE, NON-ABRIDGED engineering package that respects the user's original objectives and 0–18 numbering. Do not substitute a summary for a full deliverable. Do not silently remove, shorten, censor, rearrange or paraphrase source passages in the archival copy. Keep an untouched SOURCE_ORIGINAL and SOURCE_REVISION. Make a separate IMPLEMENTATION document using additions/patches with exact section anchors and a CHANGELOG recording original text, proposed edit, reason and source. If text is inconsistent, flag the conflict and preserve both source readings. Never fabricate missing original content.

Engineering rigor: verify vendor versions, model IDs, APIs, plans, costs, data protection requirements, platform capability scopes and relevant laws against current primary documentation. Distinguish independently verified facts from assumptions and design choices, and never pretend a sample JSON configuration is a deployed integration. Use calibrated estimates; no promises of follower growth, wealth, romantic outcomes or 'superhuman' performance. Build practical code/config/contracts and tests instead of motivational prose.

Autonomy: discover broadly and reason deeply, but only execute actions when the account owner has authorised that class of action, the tool/API officially supports it, and required consent, privacy, cost and security conditions are met. Do not design bypasses for private groups, prohibited automation, protected information or nonconsensual messaging. User-authorised, platform-supported social actions can be automatic without repetitive per-message confirmation. For other actions, explicitly state why they are unsupported or require fresh consent.

Social expression must be human-sounding, observant of verified local time, culture, stated preferences, relationship history and the other person's explicit boundaries, while staying truthful about facts and identity. Treat private adult lifestyle preferences as private; keep them isolated from LinkedIn, employer information and finances. A person's romantic interest, consent or private psychological state may never be assumed from appearance or guesswork.

Deliver the following files, with no placeholders masquerading as completed code:

01_SOURCE_ARCHIVE.md — untouched complete source provided; validate its SHA-256.
02_APEX_v4_4_INTEGRATED_SPEC.md — full 0–18 and all appendices, with all accepted changes fully developed; no elision.
03_CHANGELOG_AND_TRACEABILITY.md — source-to-target section mapping, line-level omissions check, contradictions and exact replacements.
04_CONSTITUTIONAL_AND_AGENT_PROMPTS.md — full system prompt, domain prompts, each agent's prompt and scopes. Mark any newly authored 8-1 to 8-14 prompt as NEW, not recovered.
05_SCHEMAS.sql and 06_AGENT_CONTRACTS.schema.json — real code, syntactically validated.
07_DOCKER_AND_N8N_CONFIG.md — usable sample compose/env and deployment/upgrade/rollback instructions, with secrets as environment placeholders rather than embedded values.
08_SOCIAL_CAPABILITY_MATRIX.md — vendor-by-vendor supported/unsupported/conditional capabilities, required scopes and evidence.
09_TEST_AND_SECURITY_PLAN.md — acceptance tests, leakage tests, autonomy tests, approval tests, budget tests and recovery drills.
10_SOURCES_AND_VERIFICATION.md — URLs, accessed dates, scope of verification, unknowns.

Completion gate: show counts of sections/subsections and appendices retained, list all unresolved source discrepancies and test that 0–18 appear exactly once as top-level headings. If the model hits output limits, write and save the deliverable as separate files and continue where it left off; do not compress or claim completion. The original archived file must not be rewritten by the model.

## EMPLOYER ACCOUNT / PERSONAL API BOUNDARY

The employer's Claude account must only be used for this independent personal project after written permission from the organisation. Employer-managed accounts may allow owner export or compliance review. Never insert the user's private medical/financial/relationship data or company confidential content into the employer workspace without appropriate explicit authorisation. The user's personal running system must have its own infrastructure, billing, keys and data storage. An employer Claude chat session is not a free, permanent back-end API for n8n.

## END OF IMPLEMENTATION BRIEF
