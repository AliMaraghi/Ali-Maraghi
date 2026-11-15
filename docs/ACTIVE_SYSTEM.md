# Active system — 2026-11-15

**A-10 (Social & Relational / London dating) is the ONLY active system.**
Every other system this project has built remains in code, untouched, but
does not execute via `scripts/agents_runner.py --once` unless explicitly
overridden (see `docs/FROZEN_SYSTEMS.md`).

## 3-week measurement goal

- **21 days** of log entries in `docs/a10_3week_log.md`, one row per day.
- **≥1 real message per day** sent by the owner using an A-10 draft
  (manually, after owner review — no automated send exists or is planned).
- **Metric tracked per day:** replies, conversations, meetings — not
  message volume. A day with zero sends because the owner chose not to
  is a real, loggable outcome, not a gap to paper over.

## Unfreeze condition

After 21 days, the owner reviews the log. If the system demonstrably
helped (replies/conversations/meetings happened that the owner attributes
to it), unfreeze one additional system. If not, **the system design is
questioned, not extended** — adding a second active system would repeat
the exact pattern this mission exists to stop (width before depth, no
real decision history before new scope).

A-12 (Screenwriting & Film) and A-13 (Publishing & Audience) were removed
from the manifest on 2026-11-15 because they add breadth, not depth.

## Why this, why now

26 turns produced 7 IMPLEMENTED_LOCAL roles, several additional
standalone prototypes (mutual-match platform, marketing funnel, a WebXR
digital-twin page), and zero real decisions run end-to-end with the
owner. This freeze is the mechanism, not just a stated intention, that
stops a 19th thing from being built before the first thing has been
measured for real.

## Status, 2026-11-15 (Phase 7)

- A-10 remains the one active system. The digital twin, the marketing
  funnel, the mutual-match platform, and the adult social assist module
  are frozen (`core/apex/agents_governing.FROZEN`; see
  `docs/FROZEN_SYSTEMS.md` for the honest gap on what this does and does
  not change in `agents_runner.py`'s actual execution today).
- A-12 and A-13 are deleted from the manifest, not commented out
  (`core/apex/agents_governing.py`).
- The next step is choosing a narrow domain: `scripts/choose_domain.py`
  prints the three candidates (email, bills, calendar) and the one
  question only the owner can answer. This is the one genuinely
  owner-gated piece of this whole mission — not a technical fact, a
  preference about the owner's own real life.
