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
