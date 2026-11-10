# Google personal intelligence increment

Entry91e7f5c, branch retained. Founder request additive; no source manifesto edits.
No Google access/refresh/client credential binding found in the five explicitly
checked environment names. No private secret store scan, Google Cloud project
inventory, token exchange or Gmail read was performed. ChatGPT connected Gmail
was not used and is not APEX authorization. Authorized founder identity was
provided in the directive; tests use a synthetic example identity only.

Implemented core/apex/gmail_sync.py: bounded encrypted metadata synchronization
engine requiring a separately authorized read-only API client. Uses the existing
SQLite ledger with a new google_private_sync table; private content encrypted
with caller-supplied Fernet key, not copied into public opportunity receipts.
No generated key is persisted or credentials exposed. Account identity checked
before sync. Initial unfiltered thread pages include Sent and Inbox/archive/draft
records; complete returned thread metadata is reconstructed. Default Gmail listing
excludes spam/trash. No full mailbox or attachment coverage claim. Limits20 refreshes
per step/100 retained threads are explicit pilot guards, not reduced requirements;
exceeding bounds stops without cursor advance, never silently drops records.

Incremental history reads persist pagination and only advance terminal cursor
atomically with encrypted state and audit. Thread404 removes cached thread;
history404 reports RESYNC_REQUIRED without silently re-importing. Failed fetch,
audit or identity check retains cursor. Initial capture starts history before
listing to avoid missing changes during import. Latest outgoing detection excludes
drafts/trash/spam and reports NEEDS_REVIEW, never guaranteed unanswered mail or a
real commitment. A later inbound message suppresses that candidate; resolution
through another channel remains UNKNOWN. Header content remains untrusted data.

NOT IMPLEMENTED: production Google HTTP/OAuth transport, credential refresh/store,
consent callback, Pub/Sub watch renewal, decrypted owner UI, scheduler role routing,
full mailbox backfill, attachments, durable knowledge graph, other Google adapters,
policy for mixed sensitive/employer content. No Google personal data may be imported
until that privacy boundary and actual OAuth/secure key bindings are in place.
This engine is tested with a supplied fake client, not a live integration.

Official Gmail contracts reviewed2026-11-10:
https://developers.google.com/workspace/gmail/api/guides/sync
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/list
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get

New tests exercise encryption/no plaintext audit, sent/inbound reconstruction,
wrong identity, transaction rollback, expired history and deletion propagation.
No actual Inbox, Sent, Drive or Calendar retrieval; no fabricated connection.
Full service requirements retained in GOOGLE_REQUIREMENTS.json. Production host
and Cloudflare blockers from HOST_DEPLOYMENT_BOUNDARY.json remain unchanged.
No additional infrastructure diagnosis or worker-health changes. Paid spendGBP0.
Next: implement constrained read-only Google transport and OAuth consent with PKCE,
state verification and secure key binding; do not reuse ChatGPT credentials.

Regression evidence:222 run,220 passed,2 optional dependency skips,0 failures. reports/validation/google_sync_tests.txt.
