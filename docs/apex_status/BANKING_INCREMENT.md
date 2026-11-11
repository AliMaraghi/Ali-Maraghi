# TrueLayer Data v3 connector — 2026-11-11

Status: IMPLEMENTED_NOT_AUTHORIZED (partial). Live connected bank count: 0.
No banking credentials, consent, bank data or paid requests were used.

Selected technical contract: TrueLayer Data v3. Current official documentation
recommends v3 for new integrations and states UK-only coverage. This is not a
commercial provider selection or evidence that APEX is eligible for production.
Production client eligibility, terms, and a documented zero-cost arrangement must
be established before activation. No registration or purchase performed.

Implemented core/apex/banking.py:
- reviewed read-only accounts, balance, asynchronous transaction-start and poll
  request contracts, date windows <=31 days and page size50;
- hosted-consent request body builder (does NOT submit or mount a consent route);
- real restricted HTTPS transport using existing public DNS/all-address checks
  and pinned TLS Connection, 20-second parent deadline, 1MiB response cap;
- no redirects/retries/payments, no fabricated user IP to evade bank rate limits;
- explicit owner/review/contract/consent-expiry/zero-cost checks before requests;
- approved token supplier contract with expiry and data-scope check;
- encrypted receipts within the existing single Ledger, atomic receipt+audit;
- durable intent fences: ambiguous attempts require review, never auto-replayed;
- idempotent retrieval of existing local receipts preserving observation timestamp.

Remote bodies are deliberately RECEIVED_UNVALIDATED, not LIVE_VERIFIED or
OPERATIONAL. No normalized financial projection or truthful full-sync coverage can
be claimed yet. Raw private response is encrypted; audit contains no account data.
Accounts endpoint documents max50 and inactive pagination. Transaction pagination
requires creating a new async request with the last page's next_cursor; the caller
can resume from encrypted receipts, but no automatic polling/scheduler is wired.
Token acquisition/refresh, hosted consent execution, owner-session callback binding,
connection verification, durable rate budget, retention/deletion and dashboard
registration remain NOT_IMPLEMENTED. Do not enable autonomous scheduling yet.
Permission configuration is an operator attestation, not cryptographic consent.
No provider entry was inserted into the missing original130 inventory.

Official sources checked:
https://docs.truelayer.com/docs/enable-your-users-to-connect-their-bank-account
https://docs.truelayer.com/docs/create-a-connection-v3
https://docs.truelayer.com/reference/get-accounts
https://docs.truelayer.com/reference/connected-accounts-get-balance
https://docs.truelayer.com/reference/connected-accounts-create-transactions-request
https://docs.truelayer.com/reference/connected-accounts-get-transactions-request
https://docs.truelayer.com/docs/data-v3-errors

Targeted validation: PYTHONPATH=core python3 -B -m unittest discover -s tests -p test_banking.py
5 passed. Tests check restricted requests, consent body, encrypted receipt/audit
rollback, ambiguity fencing, idempotent replay, expiry/cost checks and redirect
rejection. These are offline code checks, not bank connectivity evidence.

Next executable engineering action: bind approved credential broker and implement
verified provider connection/consent status + normalized response validation before
adding owner-facing routes or live synchronization. Exact external prerequisites:
TrueLayer Data v3 approved client, confirmed permitted pricing within GBP0,
registered HTTPS owner-session callback, and actual bank-owner consent.
