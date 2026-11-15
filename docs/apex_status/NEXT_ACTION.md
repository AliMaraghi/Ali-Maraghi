# Next Google integration operation
Read docs/apex_status/GOOGLE_ADDON_INTEGRATION.md and reports/validation/google_addon_inventory.json.
New archive is inspected; do not repeat missing-package search. Implement reviewed
Google read-only transport using pinned TLS/DNS and bounded operation contracts;
then atomic encrypted credential lifecycle. No live consent or import until actual
owner-bound OAuth/key storage and privacy review are established. Keep start/callback
unmounted until owner HTTPS/Access/session verification. Do not import reference
Store or full-format Gmail helpers. Reproduce current regression only after changes:
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py
Production deployment remains independently gated as documented previously.

Latest apex-google.zip has no code delta; see GOOGLE_ZIP_RECONCILIATION.md. Archive inspection complete. Continue constrained Google transport/token lifecycle work when requested; never copy reference store/OAuth wholesale.

2026-11-11: Constrained transport now exists in core/apex/google_http.py; see
GOOGLE_TRANSPORT_INCREMENT.md. Next implementation: encrypted expiring token broker
in existing Ledger, bound to approved OAuth owner/session, with atomic refresh/audit.
Then wire GmailClient into authorized sync; do not fetch using arbitrary credentials.
Host deployment remains blocked by authenticated executor and missing production
Access configuration; do not retry IONOS maintenance without new access evidence.

Three-track continuation: see THREE_TRACK_INCREMENT.md, BANKING_INCREMENT.md,
META_INCREMENT.md. Google encrypted broker + token HTTP + controller now exist;
next missing Google boundary is owner-session/CSRF HTTP mounting, key/client
provisioning and scheduler binding. No consent/live status is implied.

Unified web continuation: UNIFIED_WEB_INCREMENT.json. Google routes conditionally
mounted in existing ConsoleApp via /etc/apex/google-runtime.json; no separate app.
Read deployment README security/config contract. Missing config shows blocked.
Owner forms support explicit bounded sync, not recurring scheduler. Next integrate
Gmail into existing fenced job/schedule contracts without external autoactivation.
Banking receipt_projection now available; transactions inference remains blocked.

2026-11-11 connector schedule: CONNECTOR_SCHEDULE_INCREMENT.json. Gmail recurring
sync now runs through existing Schedules/worker (owner-armed, bounded, auto-disabling).
PID1 is now systemd. Deployment blocked only by owner/admin actions listed there:
root install, Access app config, tunnel DNS route, Google client/key provisioning.
Next engineering: bind banking/Meta adapters to the same connector allowlist once
their live auth exists; mobile command-centre schedule status projection.

2026-11-15: Work-account queue: empty except owner-gated criteria A and C (A-8's
planner/generator/evaluator harness has never run on a real owner ESPP/tax file;
record_outcome.py has zero real owner decisions against it - see the brutal-honesty
directive commits 56802ce..2ba34ae). Do not invent the next work item; return to
idle and wait for the owner. See docs/capability_ledger.md for Section II tool
status (zero external tools connected) and AGENTS.md's "Communication style"
section for the binding response style.
