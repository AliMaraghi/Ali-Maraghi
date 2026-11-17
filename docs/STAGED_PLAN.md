# APEX staged build plan

Written 2026-11-17. This replaces "build the whole manifesto in one go". The founder manifesto
(`docs/apex_handoff_20261109/`) stays the long-term requirement; this file is the order of work.
Rule for every stage: it extends the code that exists, and it is not "done" until the owner has
seen it work on the live server. No stage starts before the previous one is proven.

## Where we are (proven live on 2026-11-17)

Local model on the VPS (no paid API), chat with memory, 4-hourly scouts fetching real Meetup and
BBC feeds, the GBP 20 monthly hard cap, proposals-only approval gate. First 07:00 briefing is
due 2026-11-18. Known faults: the API was reachable without sign-in; the 4B model's replies
leaked reasoning (fix in `core/apex/local_llm.py`).

## Stage 0 - Safe foundations (this week)

| Work | Needs from the owner | Proven when |
|---|---|---|
| Lock `api.` and `ui.apexcorelab.uk` behind Cloudflare Access | Sign in to Cloudflare, approve the policy | A private browser window is asked to sign in |
| Server code backed up to GitHub; automatic, health-checked updates | Add one deploy key in GitHub; link GitHub to Claude | A published change appears on the server untouched |
| Budget bar and Live Scout Alerts on the dashboard | Nothing | Both panels show real numbers |
| Decide the brain: stay on 8 GB / home PC with 24 GB GPU / hourly GPU / capped paid API | A decision and, for hardware, the money | Recorded in PROJECT_MEMORY.md |

Nothing in stages 2-5 that needs judgement (critic, calibrated confidence, long plans) should be
attempted on the 4B model. Stage 1 is designed to work on it.

## Stage 1 - Money you can see (CFO, read-only)

Builds on: `core/apex/finance.py` (statement import), `agents_impl.FinancialIntelligence` (A-8),
`agent_loop.py`, the server's newer CSV parser and banking routes.
- Import the owner's own statement exports (HSBC, NatWest, Lloyds, Santander) from the inbox
  folder; one ledger; transfers between own accounts removed; categories by fixed rules.
- Monthly cash-flow, subscriptions, card balances on the dashboard, all computed in code.
- ESPP / CGT / ISA scenario from owner-supplied figures; rates checked against GOV.UK first.
- Needs: statement exports each month; ESPP plan terms; whether any benefit rules apply.
- Proven when: the dashboard totals match the owner's own bank apps for one full month.
- Later, optional: live read-only bank feed through an FCA-authorised aggregator (owner consent
  in each bank app). Payments stay blocked in code.

## Stage 2 - Events and dating support (assistive only)

Builds on: `scout_events.py`, `dating_agent.py`, `relationship_assist.py`.
- Owner's Meetup groups and other calendar feeds; weekly shortlist matched to free evenings.
- Profile and message drafting from text or screenshots the owner pastes. Owner sends by hand.
- Needs: group links; optionally Google Calendar read access (owner signs in).
- Proven when: four consecutive weekly shortlists contain at least one event the owner rates useful.
- Never: swiping, logging in, scraping or sending on any dating platform or LinkedIn.

## Stage 3 - Career and opportunities

Builds on: `scout_wealth.py`, the A-5 job shortlist, `pubmed.py` research queue.
- Reed job search with the owner's criteria; salary comparison in code; weekly digest.
- Needs: free Reed API key; the owner's target roles and salary floor.
- Proven when: the weekly digest lists live roles with correct salaries and links.

## Stage 4 - Communications and alerts

Builds on: `telegram_bot.py`, `gmail_drafts.py`, `approvals_web.py`, `kernel/approvals.py`.
- Telegram bot for alerts and one-tap approve/deny of proposals; Approve button on the dashboard.
- Gmail draft-only (never send) and calendar read.
- Needs: a Telegram bot token; Google sign-in and consent.
- Proven when: a proposal raised by the agent is approved from the phone and recorded in the ledger.

## Stage 5 - Content and studio (needs the stronger brain and its own budget)

Builds on: `twitter_agent.py`, `youtube_agent.py`, `studio.py`, `ffmpeg_plan.py`.
- Research -> draft -> five-point audit -> owner approval -> publish through official APIs only.
- Video stays a separate "Studio" budget, never drawn from the GBP 20.
- Proven when: one piece goes from idea to published with every step in the ledger.

## Stage 6 - The manifesto's upper layers (only after stages 1-4 have run for weeks)

Bi-temporal knowledge graph, adversarial critic, decision twin, and the evolution sandbox. These
need recorded real outcomes to calibrate against; building them earlier produces theatre.
Health data (Apple Health export) and coarse location belong here too, with the strictest tier.

## Permanently out of scope

Dating-platform or LinkedIn automation; NHS GP record access; unattended trades, payments or
posts; storing bank credentials; any connector reported as working without live evidence.
