# Banking receipt projection — 2026-11-11

Implemented `core/apex/banking_analysis.py`, directly consuming encrypted rows
created by the existing BankingClient in the single Ledger. It requires the same
owner/consent binding and STOP checks. No second database, fetching, key generation
or synthetic data ingestion occurs in application code.

Callable integration:
`receipt_projection(existing_banking_client, request_key)`
returns minimized account counts or strict balance minor units with original
request digest, receipt timestamp, age, privacy and verification limits. Never put
this private result into the public provider catalog or unprotected dashboard.
It belongs behind the authenticated owner boundary, not the generic public report.

Schema source checks (official docs, read2026-11-11):
https://docs.truelayer.com/reference/get-accounts
https://docs.truelayer.com/reference/connected-accounts-get-balance
https://docs.truelayer.com/reference/connected-accounts-get-transactions-request

Account response capped50; report never asserts full inventory. Names and account
numbers are omitted. Balance amounts require actual integer minor units, excluding
booleans, floats, NaN/Infinity and overflow. Currencies are not converted or summed.
Available balance can include overdraft and is not revenue; pending transactions
are not part of current balance. Age>24h is STALE; recent data is not live health.

Transactions request envelope is documented, but accessible official page did not
expose the nested result schema. Markdown page failed to load. Transaction spending,
recurrence and cash-flow inference deliberately remain BLOCKED_SCHEMA rather than
mapping v1 fields onto v3 or inventing forecasts. No commercial outcome claimed.

Targeted test command:
PYTHONPATH=core:tests python3 -B -m unittest test_banking_analysis
Observed4 pass: minor-unit safety; account identifier minimization/coverage;
unsupported transaction schema; actual encrypted receipt code-path and freshness.
These use isolated contract responses, not a live financial connection. Live bank
count remains0. Owner consent, eligible provider client and protected key binding
remain external gates; production dashboard route mounting is not done here.
