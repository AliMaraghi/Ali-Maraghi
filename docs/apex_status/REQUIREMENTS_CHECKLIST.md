# Requirements checklist (lead-owned, 2026-11-12)

Single checklist for every requested domain. Status vocabulary: DONE_OFFLINE (code + earlier tests passed),
TESTS_NOT_RUN (code written this pass, only compiled), NOT_STARTED, BLOCKED (exact blocker), UNRESOLVED_SOURCE.
No item is live-verified. Evidence = repository file. Service-level detail: `CAPABILITY_MATRIX.json`.

## Source gaps (must stay explicit)
- UNRESOLVED_SOURCE: agent IDs 8-13 and 8-14 were not supplied; remain disabled placeholders, never invented.
- UNRESOLVED_SOURCE: the pasted brief refers to specification sections 0-19; only the repository copies under
  `docs/apex_handoff_20261109/` and `/tmp/apex-manifesto-20261111.md` exist here. They were not re-read in this pass.
- UNRESOLVED_SOURCE: no Cloudflare token screenshot was ever supplied to this session.

## Finance and banking
- [DONE_OFFLINE] Enable Banking AIS client, owner-session web routes, CSV statement import: finance.py, finance_web.py
- [DONE_OFFLINE] Monzo read-only adapter: monzo.py (tests passed earlier this session before no-test pass; re-run needed after any change)
- [DONE_OFFLINE] Starling read-only adapter: starling.py (from official SDK sources; fixture-derived fields, gaps in docs/apex_status/integrations/starling.md). [BLOCKED] GoCardless (signups disabled). [BLOCKED] Yapily (licence).
- [NOT_STARTED] Per-bank CSV mappings (needs one header row per bank from the owner).

## Email and messaging
- [DONE_OFFLINE] Gmail read-only sync + token broker: gmail_sync.py, google_*.py. [DONE_OFFLINE] Gmail draft-only compose with code-level no-send: gmail_drafts.py.
- [DONE_OFFLINE] Outlook Graph draft-only (outlook_graph.py), Telegram bot notifications (telegram_bot.py), WhatsApp export importer (chat_import.py); integrated from worker A after lead review.

## Social media
- [DONE_OFFLINE] Meta Pages/Instagram read-only: meta_*.py.
- [DONE_OFFLINE] Daily snapshot schema + manual CSV fallback: social_snapshots.py (no platform API adapters yet).
- [NOT_STARTED] LinkedIn, X, YouTube, TikTok, Snapchat, Threads adapters (each needs approval/cost decision).

## Dating / relationship assistance
- [DONE_OFFLINE] Notes, manual draft packages, rule-based bio checklist, refusal guard: relationship_assist.py.
  Boundary: no account access, no automation, no impersonation, no anti-bot bypass (specification + platform policy).

## Infrastructure and networks (owner-authorised)
- [TESTS_NOT_RUN] Development console listener on 127.0.0.1:18765 (scripts/dev_console.py; not production, not tunnelled).
- [DONE live-verified on 2026-11-12] Legal pages reachable (session-served). [BLOCKED] Persistence: enable-linger needs owner sudo.
- [BLOCKED] Production /etc/apex files (approvals, google, meta, finance) need owner sudo; dev-only approvals path exists.

## Memory, evidence and agent orchestration
- [DONE_OFFLINE] Hash-chained Ledger, evidence, approvals, budget, Action Gateway: kernel/*.py.
- [DONE_OFFLINE] Universal Agent Contract validator: agent_contract.py (this pass added the 'chat' untrusted source: TESTS_NOT_RUN).
- [DONE_OFFLINE] Temporal facts with valid-time + recorded-time and as-of queries: kernel/temporal.py.
- [DONE_OFFLINE] The 18 agent slots as enforceable specifications: agents_registry.py (tier ceilings, 8-8 key-prefix limit, data-class isolation, corporate-source denial, Universal Agent Contract output check). Model runners are NOT implemented. 8-13 and 8-14 stay UNRESOLVED_SOURCE (disabled).
- [DONE_OFFLINE] Encrypted dossier with append-only access log: kernel/dossier.py (AES-256-GCM, key from a separate private file, tier-4 only for the local CLI, every attempt logged; tier-4 values must not be stored on this VPS until the owner decides).
- [DONE_OFFLINE] Decision Twin uncertainty structure, ABSTAIN rules and calibration-capped autonomy: decision_twin.py (numeric thresholds are placeholders, not from the specification). agent_contract.py gained optional `contradictions` and `estimated_cost_pence`.

## Health and location
- [DONE_OFFLINE] PubMed ESearch+EFetch adapter (pubmed.py; some parameters owner-supplied, ESearch JSON fields unverified).
- [DONE_OFFLINE] Lab-text parser (health_labs.py), OwnTracks validation + replay guard + coarsening (location_coarse.py); integrated from worker B after lead review. No persistence.
- Open owner decision: raw health/location data must stay local per specification; this VPS is not the owner's device.

## Media production and controlled evolution
- [DONE_OFFLINE] edit_package (plan only); budget with Studio pool. [DONE_OFFLINE] FFmpeg argument-array planner (ffmpeg_plan.py; segments only, no concat/scale/subtitles).
- [DONE_OFFLINE] Gateway adapter bindings (kernel/adapters.py): Gmail/Outlook drafts and owner Telegram notice, configured only with a private token file.
- [NOT_STARTED] Vendor video/voice/image adapters (need keys and registered prices). [DONE_OFFLINE] Kernel lab/evolution pointer (local only).

- [DONE_OFFLINE] Governing roster A-1..A-18 as specifications + propose-only runtime with A-1, A-5, A-8 (agents_governing.py, agents_runtime.py, agents_impl.py; 15 roles remain SPEC_ONLY). A-1 live feed BLOCKED by the reviewed endpoint scope; A-5/A-8 need owner-supplied inputs.
