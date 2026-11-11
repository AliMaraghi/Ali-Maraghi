# Three-track implementation receipt — 2026-11-11

Entry commit 6098d371139b110f0af316f48fe351c7f8102135 (newer than directive baseline).

Google: google_tokens.py adds encrypted same-Ledger credentials, expiry checks,
serialized refresh, generation/audit atomicity, local disconnect and redacted status.
google_token_http.py performs bounded pinned-TLS POST to oauth2.googleapis.com/token;
no redirects/retries, no secrets in argv/environment or error messages.
google_connect.py connects existing session-bound OAuthState to code exchange,
actual Gmail profile identity validation before installing tokens, TokenBroker,
and GmailClient token refresh. The controller requires an authenticated owner
session from its caller; it does NOT implement that session or HTTP routes.

Production callback/start endpoints remain NOT_IMPLEMENTED/unmounted. Durable
scheduler binding and console authorization UI remain NOT_IMPLEMENTED. Do not
publish endpoints until Access, HTTPS, session cookies, CSRF and client/key binding
are accepted. Controller identity strings are internal arguments, not trusted
request headers. Owner consent absent; Inbox/Sent live retrieval absent.

Credential discovery checked presence only: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, CLOUDFLARE_API_TOKEN all absent
from this execution environment. This does not establish absence in inaccessible
host secret stores. /etc/apex/access-origin.json absent. No generated replacement
key, account creation, private data import, purchases or paid API requests.

Google reference: https://developers.google.com/identity/protocols/oauth2/web-server
Refresh can succeed remotely while local commit fails; reconnect may be needed.
Local disconnect does not revoke the remote Google grant. Refresh-token expiration
and invalid_grant currently surface generic reconnect failure; automatic remote
revocation and scope-expansion flows are not implemented. Never call operational.

VPS: no new authenticated executor supplied. Earlier PolicyKit rejection not
repeated, installer not executed in isolated environment. IONOS maintenance is not
proof of VPS downtime. DNS/Tunnel/HTTPS/owner login not newly verified. Production
is BLOCKED_EXTERNAL_AUTH plus absent protected Access origin configuration.

Banking and Meta receipts are in BANKING_INCREMENT.md and META_INCREMENT.md.
No claim that the original unresolved 130-provider inventory is recovered. All
18 roles and original four planes preserved; none newly activated by this commit.

Next executable engineering action: mount GoogleConnection only after reviewed
owner session/CSRF adapter and provisioned OAuth client/Fernet key; then use
GmailSync.step(connection.client()) under explicit privacy review. Host installation
requires an authenticated administrator executor; never weaken installer gates.

Private partial adapters are now exposed by existing providers.directory with
AUTH_REQUIRED/NOT_VERIFIED states and no live receipts. Their descriptors are
implementation catalog entries, not additions to the authoritative founder list.
No new model agent, private provider connection, or production URL is operational.

Latest directive supplied the exact IONOS server panel URL. open_in_codex returned
queued; no browser control or authenticated host execution tool is exposed. No
successful login or host mutation was inferred from opening the UI.

Final regression: 262 run, 260 passed, 2 optional skips, 0 failures/errors.
Command: PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py.
An intervening run after user-message permission reset had143 sandbox filesystem/
socket errors; renewed scoped grants resolved them without changing tests.
No live acceptance, API spend or deployment occurred. Rollback is additive code
revert only; retain all existing Ledger rows and source evidence.
