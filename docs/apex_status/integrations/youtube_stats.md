# YouTube channel statistics snapshot (core/apex/youtube_stats.py) - TESTS_NOT_RUN, NOT_CONNECTED
Compiled only. Provider documentation read 2026-11-12 (developers.google.com/youtube/v3/docs/channels/list and /docs/channels): endpoint, parameters, filter rule,
response shape, statistics fields, 1 quota unit/call. Scope: `youtube.readonly` is the accepted requirement for `mine=true` (owner statement 2026-11-12; Google's scope table lists it as read-only account access; the owner wrote the scope as "https://googleapis.com", read as https://www.googleapis.com/auth/youtube.readonly). The channels.list page itself says only "properly authorized". NOT confirmed: the JSON encoding of the
counts (reference: unsigned long; code accepts ints and decimal strings), the daily quota limit. Repository policy: only `youtube.readonly` accepted; write-capable YouTube scopes refused.
Output rows follow `social_snapshots.validate_row` (platform youtube; metrics views/posts/followers; subscribers omitted if hidden; note that YouTube rounds subscriberCount).
Runtime: never run; no credentials. Remaining owner dependency: Google Cloud project with YouTube Data API v3 enabled and consent (apps in Testing mode may issue short-lived refresh tokens
per the owner-supplied hints, unverified here). PubMed: see pubmed.md.
