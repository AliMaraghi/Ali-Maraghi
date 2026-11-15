# Frozen systems — 2026-11-15 (superseded same day, see below)

Per `docs/ACTIVE_SYSTEM.md`, A-10 is the sole active system during the
21-day measurement window. Frozen means: code stays in the repository
unchanged; `scripts/agents_runner.py --once` does not execute it unless
`--include-frozen <name>` is passed explicitly (logged when used).
Freezing is not deletion and not a role-status change — no
`RoleSpec.status` value in `core/apex/agents_governing.py` was touched.

**Correction, same day:** the first version of this file froze
`{financial_intelligence, mutual_match_platform, marketing_funnel,
webxr_twin}`. A later mission this session named a different exact set —
`{digital_twin, marketing_funnel, mutual_match_platform,
adult_social_assist}` — and did not name `financial_intelligence`. The
table below reflects that later, binding set. `financial_intelligence`
is correspondingly **unfrozen** and runs by default again.

| System | Frozen date | Unfreeze condition | Why frozen |
|---|---|---|---|
| `digital_twin` (renamed from `webxr_twin`) | 2026-11-15 | Will not be unfrozen — replaced by `core/apex/kernel/behavioral_signature.py` (Phase 6) | High-risk identity mimicry (face/voice); never a runtime `agents_runner.py` agent |
| `marketing_funnel` | 2026-11-15 | Owner reviews the 21-day A-10 log (docs/ACTIVE_SYSTEM.md) | Static content (`docs/marketing_funnel_apex.md`), never a runtime agent |
| `mutual_match_platform` | 2026-11-15 | Same as above | Standalone prototype module, never a runtime agent |
| `adult_social_assist` | 2026-11-15 | Same as above | Standalone module (`core/apex/adult_social_assist.py`), never a runtime agent |

**Honest gap, named rather than hidden:** none of these 4 names match any
key in `scripts/agents_runner.py`'s `agent_factories` dict (`strategic_intelligence`,
`career_industry`, `financial_intelligence`, `health_longevity`,
`evidence_verification`, `social_relational`, `scientific_research`).
Freezing them is therefore a **no-op against `agents_runner.py`'s actual
execution** — all 7 of those roles run on `--once` today, not just A-10.
The practical effect of this freeze is the `FROZEN` registry itself
(a governance/documentation signal and a guard against ever wiring one of
these 4 into `agents_runner.py` without `--include-frozen`), not a
narrowing of today's runtime behavior. `docs/ACTIVE_SYSTEM.md`'s "A-10 is
the only active system" claim is aspirational relative to what code
currently enforces — stated plainly, not smoothed over.
