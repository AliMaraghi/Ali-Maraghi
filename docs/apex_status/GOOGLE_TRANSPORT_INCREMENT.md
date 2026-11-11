# Gmail transport increment — 2026-11-11

Entry: de7934cb3b21cec3a5f2d4db929f441f3443dba6. Production NOT DEPLOYED.

Implemented core/apex/google_http.py: GmailClient fits the existing GmailSync.step
contract and checks import review and durable STOP before obtaining credentials.
Official users/me profile, labels, bounded messages/threads/history list and
metadata-only detail GETs. SENT label filter supported. No q/full/raw/body/attachment
or write operations. Uses existing all-address public DNS validation and pinned TLS
Connection; no redirects, cookies, proxies or automatic retries. Parent process
limits each request to 20 seconds; body <=1 MiB. Token supplied over child stdin,
not argv/environment. Child errors redact upstream bodies and exception details.
Response data stays in private process memory and existing encrypted sync state.
No second ledger or changed transaction semantics.

Official contracts reviewed:
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list

Not live verified. No OAuth client, consent, production token broker, mounted
callback, token renewal or new private data. HTTP 401/403/429/5xx are surfaced as
GmailError(status); scheduling backoff and reconnect remain caller responsibilities.
The injected token supplier is not proof of consent. Production integration remains
blocked until authenticated owner OAuth, encrypted credential lifecycle, and privacy
review are bound. No banking/social/dating implementation added in this increment.
Original 130 inventory remains unresolved; this does not invent additional entries.

Targeted command: PYTHONPATH=core python3 -B -m unittest discover -s tests -p test_google_http.py
Result: 5 passed (contract/security tests, not live acceptance).
Initial full regression: 247 run, 243 passed, 2 optional skips, 2 sandbox socket
errors. Network permission requested for existing loopback tests; final result below.

Rollback: revert only this additive transport/tests and documentation commit;
no migrations or runtime records were changed. Do not delete historical data.
Final regression after loopback grant: 247 run, 245 passed, 2 optional skips,
0 failures, 0 errors. Command: PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py.
Paid API spend in this increment: GBP 0. No deployment or live Google request.
