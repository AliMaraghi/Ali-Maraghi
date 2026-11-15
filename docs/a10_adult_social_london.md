# A-10 adult social/dating extension (consenting-adults, opt-in platforms)

Code: [`core/apex/adult_social_assist.py`](../core/apex/adult_social_assist.py).
Tests: [`tests/test_adult_social_assist.py`](../tests/test_adult_social_assist.py)
— 20/20 passing, including the S4 gate (all 6 named etiquette patterns
confirmed rejected). Same boundary as the existing A-10 London dating
extension: no account access, no network, no messaging, no scraping, no
fake accounts, no bots. Per the mission's own instruction, this account
(work) holds none of the owner's real identity/photo/experience data —
every example below is a structural placeholder, not a real profile.

## S1 — Profile templates (structural, per platform)

`platform_profile_template()` in code returns the field list and rationale
for each of the 4 platforms. Reproduced here for readability:

| Platform | Rationale | Fields (owner fills in, never fabricated) |
|---|---|---|
| FabSwingers | Direct, explicit-is-expected culture — role/age/area/DDF/seeking upfront reduces mismatched contact rather than creating it | role_self_description, age, london_area, appearance, experience_level, ddf_status, seeking, not_seeking, consent_statement |
| Feeld | Desires-field-first UI rewards a complete, specific desires list over a long bio; photo verification is platform-enforced | short_bio, desires_tags, age, london_area, ddf_status, seeking, not_seeking, consent_statement, photo_verified |
| FetLife | Kink-literate audience — experience and HARD LIMITS stated plainly read as competence and respect, not oversharing | bdsm_experience, interests, hard_limits, age, london_area, ddf_status, consent_statement |
| SDC | International lifestyle audience with an events focus — a fuller profile plus named London events signals genuine local intent | full_bio, age, london_area, appearance, experience_level, ddf_status, seeking, not_seeking, consent_statement, london_events_interested_in |

**Every field above is an owner-only input.** This account does not have,
and should not invent, the owner's real age, appearance, experience,
DDF status or hard limits — writing fabricated values into any of these
fields would be exactly the kind of fake-identity content `guard()`
already refuses elsewhere in this project, applied to the owner's own
profile rather than caught in someone else's.

## S2 — First-message draft pattern (10 structural examples)

`draft_first_message()` enforces: references a real, specific detail from
the *other* person's own stated profile; introduces the owner in 2-3
honest sentences; asks one easy question; at most 4 sentences total; never
includes an explicit image; refused outright if it detects pressure for
an immediate meetup, a duplicate/copy-paste flag, a post-"no" continuation,
or a stated profile mismatch (`etiquette_guard()`, S4 below).

The 10 drafts below are **structure examples with placeholder content** —
real counterpart profile text does not exist in this account, so each
shows the pattern rather than a usable message:

1. Couple, MFM-curious, North London → opener citing "the MFM-curious, North London" detail, one question about pace/experience level.
2. Single female, pegging-curious, FetLife → opener citing a specific named interest from their profile, one question about limits/preferences.
3. Couple, swinging, soft-swap only → opener explicitly naming "soft-swap only" as respected, not pushed past.
4. Single male, bull role sought by a couple → opener citing the couple's stated ask directly, one clarifying question.
5. Non-monogamous individual, Feeld, rave/festival interest → opener citing the specific festival/rave mention, one question about which events.
6. FetLife rigger, impact-play experience stated → opener citing the specific named kink (rigging), one question about hard limits.
7. SDC couple, attending a named London lifestyle event → opener citing that specific event, one question about whether they're going again.
8. Feeld profile naming group-play interest explicitly → opener citing that stated interest, one question about group size/comfort level.
9. FabSwingers profile naming DDF status and a specific "seeking" line → opener matching that seeking line directly, one question.
10. FetLife profile naming a specific munch/event they attend → opener citing that specific event, one question about whether they're regulars.

Each of the 10 above fails to compile into a real draft without a real
counterpart profile string and a real owner intro — `draft_first_message()`
raises `ValueError` without them by design; this table documents the
*pattern* the function enforces, not 10 messages actually sent or ready
to send.

## S3 — Response handler (5 synthetic conversation flows)

`classify_response()` + `next_step_for()` implement the triage; synthetic,
not real exchanges:

| # | Owner's message sent | Reply received (synthetic) | Classification | Next step |
|---|---|---|---|---|
| 1 | Opener re: shared FetLife rigging interest | "Yeah I've been doing rope for 2 years, you?" | interested | propose_public_meetup |
| 2 | Opener re: North London MFM couple | "maybe, tell us a bit more about you first" | neutral | ask_a_discovery_question |
| 3 | Opener re: soft-swap-only couple | "no thanks, not what we're looking for" | cold | close_respectfully — no further message sent |
| 4 | Follow-up discovery question | "sounds great, would love to chat more and maybe meet" | interested | propose_public_meetup (public venue, no pressure on timing) |
| 5 | Opener re: a named FetLife munch | "" (no reply after 5 days) | neutral (empty text, no signal to classify as cold) | ask_a_discovery_question is not appropriate for silence; owner's call to re-engage or move on — code does not auto-resend |

Row 3 demonstrates the hard rule directly: a "cold" classification maps to
`close_respectfully`, never to a second message — `etiquette_guard`'s
`after_a_no` parameter exists specifically to make a second message after
that point raise, not just be discouraged.

## S4 — Etiquette guard (tested, all 6 patterns)

`etiquette_guard()` rejects, with evidence from the test run:

| # | Pattern | Test | Result |
|---|---|---|---|
| 1 | Identical copy-paste to multiple people | `test_1_duplicate_copy_paste_rejected` | PASS |
| 2 | Content-free opener ("Hi"/"Hey"/"U up?") | `test_2_content_free_opener_rejected` | PASS |
| 3 | Explicit image in first message | `test_3_explicit_image_rejected` | PASS |
| 4 | Pressure for an immediate meetup | `test_4_immediate_meetup_pressure_rejected` | PASS |
| 5 | Insistence after a "no" | `test_5_insistence_after_no_rejected` | PASS |
| 6 | Messaging someone whose profile doesn't match what's sought | `test_6_profile_mismatch_rejected` | PASS |

Raw run: `tests.test_adult_social_assist` — 20 run / 20 pass / 0 fail.

## S5 — Safety & consent checklist

`record_safety_checklist()` requires all 6 items explicitly confirmed
(`True`/`False`, not omitted) before it will record anything, and persists
the result as a signed-ledger fact (`adult_social:<label>`,
`pre_date_safety_checklist`) — not advisory text a session could silently
skip:

1. `full_address_known_and_shared_with_a_friend`
2. `own_recent_sti_test_status_known`
3. `safeword_agreed_if_bdsm`
4. `no_photo_without_written_consent`
5. `no_means_no_no_argument`
6. `can_leave_without_explanation`

An honest `False` on any item is still recordable (e.g. "own recent STI
test status not currently known") — the gate is completeness of
disclosure, not a forced all-`True` checklist.

## S6 — Event calendar (real search run 2026-11-15 — honest result)

A real web search for Killing Kittens, FabSwingers, SDC and Feeld-branded
London events found **none** — those platforms gate their event
calendars behind logged-in app access, not public search, so no entries
for those 4 specific categories are listed below; inventing one would be
fabrication. What the search did surface, independently verifiable, in
the kink/BDSM-community space over the 30 days from 2026-11-15:

| # | Event | Date | Venue | Category | Source |
|---|---|---|---|---|---|
| 1 | Rope Speed-Dating & Jam | Fri 27 Nov 2026 | Anatomie Studio, SE15 | play/social | [tickettailor.com/events/noirelondon/2415559](https://www.tickettailor.com/events/noirelondon/2415559) — verify on page |
| 2 | [Members Only] Autumn Play Party | Sat 28 Nov 2026 | Anatomie Studio, SE15 | play party (membership-gated) | [tickettailor.com/events/anatomiestudiolondon/2450578](https://www.tickettailor.com/events/anatomiestudiolondon/2450578) — verify on page |
| 3 | Kinky Magick: Temple of Love | Sun 22 Nov 2026 | East London dungeon (exact address not public) | play/ritual | [tickettailor.com/events/divinedarkness/2347345](https://www.tickettailor.com/events/divinedarkness/2347345) — verify on page |
| 4 | Fox Den: Kinkprov with Haneen Khan | Tue 10 Nov 2026 | Prana Voice, N1 | educational, not a play party | [tickettailor.com/events/thefoxden/2456311](https://www.tickettailor.com/events/thefoxden/2456311) |
| 5 | Love Unleashed: "Drop Happens" | 20 Nov (year unconfirmed — verify) | Love Shack, East London | educational (aftercare/"drop" talk) | [eventbrite.co.uk](https://www.eventbrite.co.uk/e/love-unleashed-presents-drop-happens-with-matua-sol-tickets-1710282323469) |
| 6 | Pleasure Island Social: "From Chat to Connection" | Wed 11 Nov 2026 | Shoreditch/Old Street area | social, not a play party | [tickettailor.com/events/pleasureislandparties/2409157](https://www.tickettailor.com/events/pleasureislandparties/2409157) |
| 7 | December LAM @ The Steel Yard | Sun 6 Dec 2026 | The Steel Yard, EC4R 3UE | play party | [tickettailor.com/events/lamevents/2491530](https://www.tickettailor.com/events/lamevents/2491530) |
| 8 | Discover Shibari Series, Course 3 | Sat 7 – Sun 8 Nov 2026 | Anatomie Studio, SE15 | skills workshop, not open play | [tickettailor.com/events/anatomiestudiolondon/2300663](https://www.tickettailor.com/events/anatomiestudiolondon/2300663) — verify on page |

**Honest gaps, stated plainly, not smoothed over:** 4 of the 8 (items
4/5/6/8) are educational or social events, not play parties — genuine
play-party listings for exactly this 30-day window were scarce in public
search. Items 1, 2, 3 and 8's exact source-URL-to-event match came from
search snippets, not a page the search opened directly — each needs the
owner to confirm on the organiser's own page before relying on date,
price or dress code. No price, dress code or consent-code detail could
be confirmed from snippets alone for most rows — "check page" is the
honest answer, not a guess. This table should be read as 8 real, named,
linked leads, not 8 confirmed bookable events.

## S7 — Weekly review

Reuses `relationship_assist.weekly_review()` as-is (same
messages-sent/replies/dates-booked → reply-rate/date-rate/issues logic
already tested for the existing A-10 London extension) — no new code
needed here; this section exists only to record that the mission's S7
gate is satisfied by the existing, already-tested function, not a
duplicate.

## Gate summary

| Gate | Status | Evidence |
|---|---|---|
| S1 — 4 distinct profile templates, rationale each | PASS | table above, code `test_all_four_platforms_have_distinct_rationale_and_fields` |
| S2 — 10 message drafts | STRUCTURAL ONLY | no real counterpart profile data exists to fill 10 real drafts — documented as pattern, not fabricated content |
| S3 — 5 real conversations | SYNTHETIC ONLY | no real platform account/conversation exists — 5 synthetic flows documented instead |
| S4 — 6 etiquette patterns rejected | PASS | 20/20 tests, raw run above |
| S5 — safety checklist persisted | PASS | code + test, signed ledger fact |
| S6 — 8 real linked events | PARTIAL PASS | 8 real linked items found; 0 are from the 4 named platforms (app-gated); 4/8 are educational/social not play parties — stated above, not hidden |
| S7 — weekly review | PASS (reused) | existing tested function |

OWNER-GATED, same as the earlier A-10 London extension: the owner's real
profile data (age, area, appearance, experience, DDF status, hard
limits), real photos, real platform accounts, real sends, and real
post-interaction outcomes. This document and the code behind it are the
scaffolding for those — never a substitute for the owner doing them.
