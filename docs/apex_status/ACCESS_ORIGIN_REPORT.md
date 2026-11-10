# Access origin increment

Entry4ae94b2, existing branch retained. Implemented core/apex/kernel/access_auth.py
and integrated it into the existing owner-view CLI via --access-config. No second
dashboard or database. Existing Basic mode is still development-only; Access mode
never falls back to it. Access mode is a foreground supervisor target with graceful
SIGTERM/SIGINT, loopback binding and per-request identity checks. No service installed.

Validation: pinned RS256, administrator-configured exact team issuer and audience,
owner email, required signed claims, finite integer times, expiration, distinct bounded
public RSA keys. No token-controlled key URL fetch. A trusted local JWKS snapshot must
come from the exact team /cdn-cgi/access/certs endpoint and expires within24h. Unknown
keys fail closed. Snapshot expiry denies access until reviewed refresh and restart.
No automatic refresh or live Cloudflare policy verification is implemented.

Official contract reviewed2026-11-10:
https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/

Configuration fields: issuer (https://TEAM.cloudflareaccess.com), audience (actual64hex
application AUD), owner_email (exact identity), retrieved_at/expires_at (integer UTC
Unix seconds, at most24h apart), source_url (issuer+/cdn-cgi/access/certs), jwks
(actual official response containing keys). These must be recovered from authorized
configuration; placeholders/test keys MUST NOT be used for deployment. File must be
regular, <=32KiB and not group/world writable. Public keys are not management secrets.

Executable command after configuration exists:
python3 -B scripts/apex owner-view --trace ted-fresh-20261110-v3 --access-config /etc/apex/access-origin.json

Tests use generated RSA keys, actual verification and loopback HTTP requests; they
are offline authentication tests, not successful Cloudflare logins.208 tests run,
206 passed,2 optional FastAPI/httpx skips. Tested installed PyJWT2.7.0 and
cryptography41.0.7; dependency security review and isolated production lock remain
open. Standard-library HTTP server lacks production load/rate-limit validation.
Do not publish until production packaging, owner policy, actual signed-token test,
TLS and denied-access tests pass. No claim of production readiness.

Actual network: FTS root HTTPS200, PyPI HTTPS200, Cloudflare public API root403;
DNS resolution succeeded for each. Cloudflare403 does not prove management access.
Known token env references absent; /etc/apex and ~/.cloudflared absent. No secret
values read or printed. No Git remote configured. cloudflared system service active;
tunnel health and identity remain unverified. Prior privileged-installation blocker
was not retried or bypassed. SSH agent presence alone is not verified SSH access;
connecting back into this same host to evade sandbox restrictions is prohibited.

No paid API use, new field trace, new integration, financial result, DNS change,
production deployment or independent benchmark claimed. Full target remains open.
Rollback this code commit without resetting source archives or database history.
