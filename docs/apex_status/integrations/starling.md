# Starling Bank read-only adapter (core/apex/starling.py)

Status: TESTS_NOT_RUN. Live status: NOT_CONNECTED. No network call to Starling was made; no account data seen.
Only compile check run (py_compile). Sources were fetched via WebFetch, which summarises pages, so quoted
values below are as reported by that summariser from the raw files.

## Provenance per detail
| Detail | Source |
|---|---|
| Default host https://api.starlingbank.com (sandbox api-sandbox.starlingbank.com not used) | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/src/starling.js (defaults.apiUrl); sandbox only in README.md |
| Auth: Authorization: Bearer <token>, Accept: application/json | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/src/utils/http.js (defaultHeaders) |
| GET /api/v2/accounts | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/src/entities/account.js (getAccounts) |
| GET /api/v2/accounts/{accountUid}/balance | account.js (getAccountBalance, accountUid validated as uuid) |
| GET /api/v2/feed/account/{accountUid}/category/{categoryUid}?changesSince=<timestamp> | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/src/entities/feedItem.js (getFeedItemsChangedSince) |
| Account fields accountUid, defaultCategory, currency (also createdAt, unused) | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/test/responses/v2-get-accounts.json |
| Balance fields clearedBalance, effectiveBalance, pendingTransactions (+acceptedOverdraft, amount, unused), each {currency, minorUnits} | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/test/responses/v2-get-account-balance.json |
| Feed fields feedItems[], feedItemUid, categoryUid, amount{currency,minorUnits}, direction, updatedAt, transactionTime, settlementTime, status, counterPartyName, reference; status values PENDING, SETTLED; direction value OUT | https://raw.githubusercontent.com/starlingbank/starling-developer-sdk/master/test/responses/v2-get-feed-items.json |
| Timestamp example format '2019-10-25T12:34:56.789Z' | feedItem.js JSDoc |

## Uncertain / not implemented
- Response schemas come from SDK test fixtures, not a live or official API reference. The docs site (developer.starlingbank.com/docs) needs JavaScript and yielded nothing.
- direction "IN" is NOT shown in the fixture (only OUT). The brief says IN is positive; this is implemented as the obvious counterpart but is unconfirmed by source.
- Other status values (e.g. declined/reversed) are not shown; any unknown status or direction makes the call fail with INVALID_RESPONSE rather than guessing.
- Account name and account type fields are not shown in fixtures; they are not returned.
- Whether changesSince filters on updatedAt is inferred from the name; the cursor uses updatedAt on that assumption.
- The SDK shows no paging/size parameter or server-side limit; only one request per call, bounded by MAX_ITEMS=5000 and 1 MB (PAGE_LIMIT_REACHED / INVALID_RESPONSE). If a server truncates silently this adapter cannot tell.
- Rate-limit behaviour, token scopes and personal-access-token issuance were not confirmed by any source.
- Amounts: negative minorUnits are rejected for feed items (sign comes from direction).

## Contract
Mirrors core/apex/monzo.py: injectable transport(method, path, headers) -> (status, content_type, bytes); token None -> StarlingError('NOT_CONFIGURED'); errors STARLING_HTTP_<status>, INVALID_RESPONSE, PAGE_LIMIT_REACHED, never include path, token or upstream body. READ_ONLY_OPERATIONS = {accounts, balance, feed_changes}; request() refuses others; live_transport refuses non-GET and uses Connection (5 s timeout in public_http). No payment/transfer/payee/standing-order/savings-goal code exists.

Cursor: next_cursor = newest updatedAt minus 300 s overlap, never earlier than the input cursor, unchanged when no items. Overlap re-delivers items; upsert_items keys by "<accountUid>/<feedItemUid>" so PENDING becomes SETTLED in place.

Token file: load_token(path): lstat regular file (symlink rejected), mode & 0o077 == 0, owner current user or root, <= 4096 bytes, ASCII single line matching a conservative regex; absent -> NOT_CONFIGURED, unsafe -> ValueError with no token content. redact() masks Authorization values, bearer tokens and long token-like strings (this also masks UUIDs, deliberately).
