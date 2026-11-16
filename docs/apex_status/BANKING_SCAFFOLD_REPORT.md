# Banking connector scaffold — 2026-11-16

## What was requested
A request to make "all API connections ... fully operational" for dating apps,
adult content/dating platforms, banking and wealth. That request was declined
as stated; see the chat record for the reasoning. The one legitimate piece —
a structural, non-live banking connector scaffold — was built on request.

## What exists now
`core/apex/banking_connect.py` — `BankingConnection`, modelled on the existing
`meta_connect.py` pattern (owner-session-bound consent, encrypted token storage
in the existing Ledger, `AUTH_REQUIRED` default status, no credentials in logs
or audit).

Differences from `meta_connect.py`, stated explicitly because they matter:
- No aggregator (TrueLayer / Nordigen-GoCardless Bank Account Data / Plaid /
  other FCA-regulated AISP) has been chosen or reviewed. `meta_connect.py`
  hardcodes Facebook's real, documented Graph API; this module cannot do the
  equivalent because there is no reviewed real endpoint contract yet. Host,
  paths and client credentials are 100% operator-supplied config — nothing is
  guessed or defaulted.
- Scope is permanently restricted to read-only Account Information (AIS).
  `require_read_only()` hard-rejects any scope string containing `pisp` or
  `payment` before a consent URL is ever built. Payment Initiation (moving
  money) is out of scope for this module, period — not a missing feature.
- `accounts()` projects only `id` / `display_name` / `currency`. Sort code and
  account number are explicitly never carried past the aggregator response,
  the same pattern `meta_readonly.py` uses to drop upstream access tokens.

## What does NOT exist
- No real aggregator client_id/secret, no live HTTP calls, no live consent.
- No HTTP route mounted (`banking_connect.py` has no web layer yet, unlike
  `meta_connect.py` + `meta_web.py`).
- No wealth/investment/brokerage connector of any kind.
- No dating/adult-platform connector — none of those four platforms publish a
  partner API, and automation violates their Terms of Service; this was not
  attempted.

## Evidence
`tests/test_banking_connect.py` — 7/7 passing, including:
- `test_defaults_to_auth_required` — no connection means no access.
- `test_construction_rejects_payment_scope` / `test_payment_scope_rejected` —
  the payment-scope block is enforced at construction and at the scope
  validator, not just documented.
- `test_full_flow_encrypts_token_and_rejects_replay` — tokens never appear in
  plaintext in the Ledger dump; a consumed state cannot be replayed.
- `test_account_number_never_in_projection` — sort code / account number sent
  by the (mock) aggregator are confirmed stripped before returning to the
  caller.

Full suite after this change: 781 run / 779 pass / 2 skip / 0 fail
(`PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py`).

## Next step, if ever actually wanted
Pick one real, FCA-regulated AISP, get its real developer docs, review its ToS
and pricing, then fill in `config` with its real host/paths — nothing in this
module should be extended to hardcode a provider that hasn't been reviewed.
