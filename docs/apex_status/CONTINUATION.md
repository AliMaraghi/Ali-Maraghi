# APEX continuation (read first)

Updated 2026-11-11. Branch apex/unified-field-integration. Offline suite 295 run / 293 pass / 2 skip.

## Production state (verified by probe, not by report)
- Cloudflare: Access app + tunnel route + DNS live. Team `wispy-limit-fad4`, AUD verified
  by RS256 signature of the edge redirect. Anonymous HTTPS -> 302 to Access login.
- Host: units NOT installed until `/tmp/apex-install-receipt.txt` shows EXIT1=0, EXIT2=0.
- Claude Code runs inside root SSH pts/1 via `runuser -l apexdev`; text typed while Claude is
  open is chat, not shell. Root action: `/exit`, run activate.sh, resume with
  `runuser -l apexdev -c 'cd /home/apexdev/apex-work && /home/apexdev/.local/bin/claude --continue'`.
- Single root action: `sh /home/apexdev/apex-work/deploy/production/activate.sh 'OWNER_EMAIL'`.

## Verify after install
`python3 -B scripts/production_acceptance.py` (read-only). Then founder phone login, other-email
denial, `systemctl restart apex-console apex-worker` recovery, reboot persistence.

## Pre-verified locally (DB backup copy, ephemeral key)
Console: owner 200 (12-section Founder Command Centre), other email / no token 401.
Worker cycle completes; health fresh. Stale `fresh-review` schedule is isolated, not starving.

## Root provisioning after activation (each: /exit Claude first, root shell, then resume)
- Google: `python3 -I -B /home/apexdev/apex-work/deploy/production/provision_google.py`
  (needs Google Cloud OAuth Web client; redirect https://console.apexcorelab.uk/auth/google/callback;
  Gmail API enabled; consent screen Testing with founder as test user -> refresh token expires 7 days,
  reconnect weekly until app verification for restricted scope gmail.readonly).
- Meta: `python3 -I -B /home/apexdev/apex-work/deploy/production/provision_meta.py`
  (Meta app, Development mode, founder admin; Facebook Login redirect
  https://console.apexcorelab.uk/auth/meta/callback; scopes pages_show_list,
  pages_read_engagement, instagram_basic; long-lived token ~60 days).
- Finance (9 mandatory targets, core/apex/finance.py + finance_web.py, /connections/finance):
  `python3 -I -B /home/apexdev/apex-work/deploy/production/provision_finance.py` generates RSA key on
  server, prints public cert. Owner registers Enable Banking app (Control Panel, restricted mode =
  own linked accounts, no contract) with redirect https://console.apexcorelab.uk/auth/finance/callback,
  then reruns script to bind app UUID. Coverage per target comes from live GET /aspsps?country=GB.
  PayPal/NewDay direct AIS needs FCA-authorised TPP; if aggregator does not list them -> statement
  import: `scripts/apex finance import --account paypal --file F.csv --format paypal` (IMPORTED, not LIVE).
  GoCardless BAD new signups disabled (official notice). TrueLayer adapter kept; needs commercial go-live.

## Unified connections (2026-11-11 mandate A-M)
core/apex/declared_targets.py: 45 founder-declared targets in 11 compartments, reconciled into
connectors CLI and console /connections. States derive only from Ledger receipts. Production-copy
result: 1 LIVE_PUBLIC_RECEIPT (Crossref #79), 12 IMPLEMENTED_NOT_AUTHORIZED, 12 IMPORT_NOT_IMPLEMENTED,
15 NOT_IMPLEMENTED, 2 BLOCKED_BUDGET_APPROVAL (X, Anthropic API), 3 EXISTING_PUBLIC_CONNECTOR.
health/intimate/dating compartments excluded from briefings by default. verify=True rows need
re-check against current provider docs before implementation.

## Next engineering
1. After live consent: verify Gmail profile/INBOX/SENT labels via /connections/google/sync, arm schedule.
2. Meta: connector allowlist entry for scheduled page discovery after first live success.
3. Generic encrypted data-export importer (dating/adult/social/health documents), compartment-bound.
4. YouTube Data API on existing Google OAuth client; Threads via Meta app.
5. Daily founder briefing + credential-expiry warnings projected into console from Ledger.
Live providers operational: none. 18 agents / 130 providers: not live-verified.
