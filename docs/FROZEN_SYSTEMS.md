# Frozen systems — 2026-11-15

Per `docs/ACTIVE_SYSTEM.md`, A-10 is the sole active system during the
21-day measurement window. Frozen means: code stays in the repository
unchanged; `scripts/agents_runner.py --once` does not execute it unless
`--include-frozen <name>` is passed explicitly (logged when used).
Freezing is not deletion and not a role-status change — no
`RoleSpec.status` value in `core/apex/agents_governing.py` was touched.

| System | Frozen date | Unfreeze condition | Why frozen |
|---|---|---|---|
| `financial_intelligence` (A-8) | 2026-11-15 | Owner reviews the 21-day A-10 log; if it demonstrably helped, unfreeze one additional system (docs/ACTIVE_SYSTEM.md) | Is an actual `agents_runner.py` runtime agent; not the active system for this measurement window |
| `mutual_match_platform` | 2026-11-15 | Same as above | Named by the mission as a system to freeze; in practice was never registered in `agents_runner.py` (confirmed by grep — zero references) — it is a standalone prototype module, so "frozen" here is a documentation state, not a code change |
| `marketing_funnel` | 2026-11-15 | Same as above | Static content (`docs/marketing_funnel_apex.md`), never a runtime agent — same caveat as above |
| `webxr_twin` | 2026-11-15 | Same as above | Static page (`digital_twin/phase1_room.html`), never a runtime agent — same caveat as above |

**Honest gap, named rather than hidden:** `docs/ACTIVE_SYSTEM.md` declares
A-10 the *only* active system, but this table (and the `FROZEN` dict in
`agents_governing.py`) freezes only the 4 systems the mission explicitly
named. The other 5 IMPLEMENTED_LOCAL roles that `agents_runner.py` also
runs today — A-1 (Strategic Intelligence), A-2 (Scientific Research), A-3
(Evidence & Verification), A-5 (Career & Industry), A-15 (Health &
Longevity) — are **not frozen in code** and will still execute on
`--once`. Freezing them was not in this mission's explicit list, and
"do not flip any role" / "only these two changes, no new scope" argued
against silently adding them. This means Gate P2's "only A-10 runs" does
not fully hold yet — see the session report for the precise gate result.
