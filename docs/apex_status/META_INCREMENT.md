# Meta read-only increment — 2026-11-11

Status: IMPLEMENTED_NOT_AUTHORIZED (partial capability only). No Meta account
request, consent, token provisioning, external mutation or paid API call occurred.

## Implemented
- `core/apex/meta_readonly.py`: fixed graph.facebook.com GET transport for
  `/VERSION/me/accounts?fields=id,name,instagram_business_account&limit=20`.
- Existing all-address public DNS validation and pinned TLS Connection reused.
  No redirects/proxies/cookies; hard20-second subprocess deadline;1MiB response.
  Token goes through subprocess stdin, never argv/environment or audit.
- Explicit app ID, owner, externally verified grant reference, scopes, grant
  expiry, privacy review and operator-reviewed Graph version binding. No default
  version is invented. This binding is caller attestation, not proof of consent.
- Facebook Page discovery and linked Instagram professional-account identifiers.
  Credentials and unexpected fields are removed by explicit projection.
- Pagination uses bounded `after` cursor; upstream `next` URL is never fetched or
  retained because it can contain credentials or arbitrary destinations.
- Existing Ledger additive encrypted snapshot/cursor + redacted audit committed
  atomically using the existing transaction contract. STOP, expiry, 20-page-items
  and100-total-Page pilot caps; completed pagination reports historical completion,
  not current health or full platform connectivity. No second database.
- `PROVIDER` capability descriptor is available to the existing catalog. It is an
  implementation descriptor, not a recovered founder inventory entry or live count.

## Official evidence and limits
Retrieved through web tools2026-11-11:
https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-8bbca62a-dbc8-4c01-b724-09ed5e2b82f8
Meta-maintained collection confirms Graph me/accounts, managed Page fields and
linked instagram_business_account. The implementation deliberately omits returned
Page access tokens. It uses Facebook Login scope family, not Instagram Login.
https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/get-started
Direct documentation retrieval returned HTTP429; no claim that all latest-version
fields or current lifecycle policy have been validated. Active app API version
must be confirmed in its official developer configuration before activation.

## Not implemented / external gates
OAuth start/callback/code exchange, encrypted token broker/renewal/revocation,
provider dashboard mounting, Instagram media and insights, Facebook Page posts,
webhooks and WhatsApp Business are NOT_IMPLEMENTED by this module. No personal
Instagram messages or arbitrary Facebook private messages are supported.
Production gating: actual Meta developer app, supported reviewed version, owner
identity/session binding, secure callback, app review/access eligibility where
required, actual pages_show_list/pages_read_engagement/instagram_basic grants,
protected token broker, reviewed private-data retention/deletion. No credential
values should be copied into chat. No claim of operational social connectivity.
HTTP failures surface without upstream private bodies; no automatic retry occurs.
Rate-limit/backoff scheduling remains an integration requirement. Completed pilot
snapshots do not refresh automatically; explicit reviewed reset/retention workflow
is required for a new account inventory. Encryption keys must persist securely.

## Verification
Command: PYTHONPATH=core:tests python3 -B -m unittest test_meta_readonly
Observed:4 passed. These are contract/security tests, NOT live acceptance.
Covers credential minimization, cursor URL refusal, invalid versions, permissions
and expiry, encrypted persistence, rollback after audit insertion, completed-state
no-refetch, HTTP redirect rejection without reading body. No live claims.
Rollback: remove only the additive module/test in a reviewed code revert; preserve
existing database and additive historical rows. No production migration was run.
