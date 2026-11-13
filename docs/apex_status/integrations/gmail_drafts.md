# Gmail draft-only adapter (core/apex/gmail_drafts.py) - TESTS_NOT_RUN, NOT_CONNECTED

Verified on 2026-11-12 from developers.google.com:
- users.drafts.create: `POST https://gmail.googleapis.com/gmail/v1/users/{userId}/drafts` (`me` = authenticated user). Scopes accepted: `https://mail.google.com/`, `.../auth/gmail.modify`, `.../auth/gmail.compose`.
- Draft resource fields: `id`, `message` (Message). Message.`raw`: "The entire email message in an RFC 2822 formatted and base64url encoded string."
Not confirmed from the pages fetched: exact success response fields beyond `id`/`message`, rate limits, size limits for `raw`.

Policy in this repository (not a Google statement): only `gmail.compose` (+ optional `gmail.readonly`) is accepted. Broader scopes (`mail.google.com`,
`gmail.modify`, `gmail.send`, ...) are refused by `assert_draft_scopes`. The owner-supplied API hints say compose can also permit sending, so
no-send is enforced in code: the module has no send function and a guard refuses any method/path other than POST /gmail/v1/users/me/drafts,
even from a custom transport. Missing token -> `NOT_CONFIGURED`. The owner reviews and sends manually in Gmail.
Gateway binding: `gmail_draft` kind + `kernel/adapters.py` `GmailDraftAdapter` (configured only when a private token file loads).
