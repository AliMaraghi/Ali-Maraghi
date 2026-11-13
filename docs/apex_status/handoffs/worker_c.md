# Worker C handoff: Starling read-only adapter

Task: new core/apex/starling.py mirroring monzo.py, sourced only from the official Starling developer SDK.
Baseline: /tmp/claude-1000/-home-apexdev-apex-work/5f5e302b-9067-458f-887d-4f5b6fe6916e/scratchpad/work_c
Changed files: core/apex/starling.py, docs/apex_status/integrations/starling.md, docs/apex_status/handoffs/worker_c.md

Public interfaces:
- HOST, READ_ONLY_OPERATIONS, StarlingError
- request(op, token, transport, **args) -> dict
- live_transport(method, path, headers)
- load_token(path) -> str; redact(text) -> str
- list_accounts(token, transport) -> [{account_uid, default_category, currency}]
- get_balance(token, account_uid, transport) -> {cleared, effective, pending: {minor, currency} | None}
- normalize_feed_item(item, account_uid, source="starling-api") -> ledger transaction dict
- fetch_feed_changes(token, account_uid, category_uid, transport, cursor) -> {items, next_cursor}
- upsert_items(existing, items) -> {merged, changed}

Verified: py_compile passed (PYTHONDONTWRITEBYTECODE=1 python3 -B -m py_compile). Endpoint paths, host, Bearer auth, query name and fixture field names traced to SDK sources (see integration doc).
Unverified: TESTS_NOT_RUN (no tests added or run); no live call; IN direction, other statuses, name/accountType, paging, rate limits unconfirmed; live_transport and strict_json integration untested; redact masks UUIDs too.
Blockers: none for code; live use needs a private token file and owner approval. Status NOT_CONNECTED.
