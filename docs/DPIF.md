# Digital Presence Integrity Framework (DPIF) — v0.1

**This is a project-specific governance specification for APEX's Digital Twin
extension. It is not an externally certified standard, has not been reviewed
by any outside body, and must not be described as one.** It exists so that
"compliant" has a checkable meaning inside this repository, and so a reader
can tell, per control, whether something is actually enforced by running code
today or is a policy statement with nothing behind it yet.

Status date: 2026-11-15. Authored alongside `core/apex/kernel/persona.py`
(subsystem 2.E of the Digital Twin directive). Versioned: any change to a
control's definition or its critical/non-critical status is a new version
number with a dated changelog entry at the bottom of this file, never a
silent edit.

**Per the directive's own rule: failure of a mandatory critical control is a
release blocker.** A "release" here means activating ANY part of subsystems
A–D (avatar rendering, voice synthesis, lip-sync, XR) for real use — nothing
in those subsystems exists yet, so no release gate has been reached, and no
control below is being claimed as a basis for one.

## Status legend

- **ENFORCED_IN_CODE** — a real, tested mechanism exists and this repository's
  test suite exercises it. File:line or test name given as evidence.
- **POLICY_ONLY** — stated as a rule in this document or the governing
  directive, but no code currently enforces it. Must not be described as
  "compliant" until it is.
- **NOT_SUPPORTED_KNOWN_GAP** — the current architecture cannot do this, and
  faking it would be worse than leaving it open. Stated explicitly, with the
  reason and what a real fix would require.

## The 18 controls

### Critical (14) — failure of any one blocks activating subsystems A–D

| # | Control | Status | Evidence / reason |
|---|---|---|---|
| 1 | Identity & voice authorisation | ENFORCED_IN_CODE | `persona.write_persona_card()` requires an explicit `voice_authorized: bool` attestation; refuses a non-boolean. Cannot verify real-world consent — only refuses to omit the attestation. |
| 2 | Clear disclosure of synthetic identity | ENFORCED_IN_CODE | `persona.write_persona_card()` refuses an empty/blank `disclosure_text` (`tests/test_persona.py::test_disclosure_text_is_mandatory`). |
| 3 | Immediate owner-controlled shutdown | POLICY_ONLY | No runtime avatar/voice process exists yet to shut down. Must be built alongside subsystem B before any real-time session ships. |
| 4 | Owner-controlled data export | ENFORCED_IN_CODE | `persona.export_persona_memories()` — read-only, real (`tests/test_persona.py::ExportTests`). |
| 5 | Owner-controlled data deletion | **NOT_SUPPORTED_KNOWN_GAP** | This Ledger (`core/apex/kernel/memory.py`) is append-only by design (hash-chained `events` table has `events_no_update`/`events_no_delete` triggers; `facts.py`'s table is append-only by convention). True erasure needs a separate, non-append-only, likely encrypted store — a real architectural decision for the owner, not built here. `persona.py` deliberately exposes no delete/forget/erase function (`tests/test_persona.py::test_no_delete_function_exists_that_could_pretend_to_erase_anything`) rather than fake one. |
| 6 | Shared/private memory boundary between personas | ENFORCED_IN_CODE | `persona.recall()` raises `PersonaIsolationError` rather than silently filtering (`tests/test_persona.py::MemoryIsolationTests`). |
| 7 | No unauthorised camera/microphone activation | POLICY_ONLY | No sensor-access code exists in this repository at all; nothing to enforce yet, nothing to falsely claim either. |
| 8 | No unauthorised third-party data collection | POLICY_ONLY | Same as #7 — no integration exists; see `docs/capability_ledger.md` (zero Section II tools connected). |
| 9 | No manipulative attachment or dependency strategies | POLICY_ONLY | A behavioural/prompt-level rule (directive section 3), not something static analysis can verify. Needs a conversation-review process once subsystem B exists, not before. |
| 10 | No false claims of consciousness, suffering, or human emotional need | POLICY_ONLY | Same category as #9 — enforceable only once there is a real conversational output to review. |
| 11 | No self-approval or agent-identity shortcut for any persona-affecting action | ENFORCED_IN_CODE | Inherited directly from `kernel.approvals.ApprovalBook.issue()`: refuses `AGENT_PREFIX` identities and self-approval, proven generically in `tests/test_capability_tokens.py`. No persona-specific Gateway kind exists yet to exercise this end-to-end for persona actions specifically — carried as a follow-up, not a gap in the underlying mechanism. |
| 12 | Append-only provenance for every memory (timestamp + source) | ENFORCED_IN_CODE | Every `persona.remember()`/`write_persona_card()` call goes through `facts.assert_fact()`, which requires a non-empty `source` and records `asserted_at`. |
| 13 | Tamper detection on stored records | PARTIAL — ENFORCED_IN_CODE for the hash-chained `events` table only | `Ledger.audit_chain()` (Phase 4) detects tampering in the `events` table. **Persona cards and memories live in the `facts` table, which is append-only by convention only and is NOT hash-chained** — a direct SQLite edit to a `facts` row would not be detected today. This is a real, disclosed gap distinct from #5; closing it would mean extending `facts.py` with the same digest-chaining `memory.py` already uses for `events`, not yet done. |
| 14 | Human-gated approval for any persona-affecting proposal | ENFORCED_IN_CODE (mechanism), POLICY_ONLY (persona-specific wiring) | `ActionGateway`/`ApprovalBook`'s existing human-gate (proven across this session's Phase 1–3 work) applies to any Gateway kind — but no persona-specific kind (e.g. "persona_voice_change_proposal") has been defined yet, so there is nothing persona-specific to gate today. |

### Non-critical (4) — tracked, not release-blocking

| # | Control | Status | Evidence / reason |
|---|---|---|---|
| 15 | Latency and performance claims must be measured, not asserted | POLICY_ONLY | Directive section 2.C's own rule ("Do not represent an unverified latency target as an achieved result"); nothing to measure yet since subsystem B/C don't exist. |
| 16 | DPIF must never be described as an externally certified standard | ENFORCED_IN_CODE (this document) | This file's own header states it explicitly; any future reference to DPIF elsewhere in the repo must repeat this, not drop it. |
| 17 | Separate, independently editable persona configurations under one governed boundary | ENFORCED_IN_CODE | `persona.write_persona_card()`/`persona_card_history()` — distinct `persona_id`s, distinct cards, distinct memory namespaces (#6). |
| 18 | This specification is versioned; no silent edits to control definitions | ENFORCED_IN_CODE (this document) | See the changelog below; any future edit adds a dated entry rather than rewriting history. |

## What "compliant" means today, stated plainly

Of the 14 critical controls: **8 are ENFORCED_IN_CODE** (1, 2, 4, 6, 11, 12, and 13/14
partially), **1 is a disclosed, currently-unsolvable architectural gap** (5),
and **5 are POLICY_ONLY with nothing built yet** (3, 7, 8, 9, 10) because the
subsystems they govern (real-time voice, sensors, live conversation) do not
exist in this repository. **No subsystem A–D activation is compliant with
DPIF v0.1 today, because none of subsystems A–D have been built at all** —
this document governs what must be true before they are, not a retroactive
label for something already shipped.

## Changelog

- **v0.1 (2026-11-15):** Initial version, authored alongside
  `core/apex/kernel/persona.py`. 18 controls defined, 14 marked critical.
