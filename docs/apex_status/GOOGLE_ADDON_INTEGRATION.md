# Reviewed Google rebuilt addon integration

Entry40968be on apex/unified-field-integration. User request governs the work;
CODEX_MERGE_INSTRUCTIONS.txt was treated as package guidance, not new authority.
All12files were read in full. ZIP SHA256:
e8d7e570f264f3992ece0a8ee7f74383daa7759f159b46c8a9b966e4b60d0e07.
All11 listed internal hashes match.12regular members/54645uncompressed bytes;
no duplicate names, symlinks or traversal. Original ZIP unchanged in attachment.
Ignored review extraction:work/review-kit/google-rebuilt-20261111. No package
installer/build hooks executed. Existing environment requests/cryptography used;
pytest8.3.5 added only to ignored work/google-review-deps. This is not a verified
production dependency lock matching the package's declared cryptography range.

Reference tests reproduced:26passed (synthetic/mock). Adverse probes separately
confirmed token survives an injected OAuth audit failure while audit count stays0,
and mailbox_message requests format=full. See google_addon_adverse_probes.json.
Those are real failures of the reference's atomicity/minimization expectations,
not failures silently skipped from production code. Static review additionally
found no session binding for OAuth state, no IP-pinned DNS/proxy isolation or hard
whole-response deadline in transport, separate weaker audit store, and incomplete
atomic pagination/deletion handling in non-Gmail syncs. Photos ready-state ignores
next page; tasks list pagination/resume incomplete. Do not import wholesale.

Selected adaptation:
- core/apex/google_policy.py: explicit per-source caller-attested privacy review,
  exact owner, strictTrue confidentiality review, reviewed service, bounded retention
  declaration and review reference. Missing/mismatched policy blocks client calls.
  This is NOT cryptographic owner approval, consent, retention enforcement or proof
  that employer content is safe. No live import until actual review is recorded.
- core/apex/google_oauth_state.py: PKCE S256 and600second state, encrypted verifier,
  exact HTTPS callback allowlist, binding to owner session/client/redirect/account,
  max10pending attempts, one-time consumption, strict expiry, STOP enforcement and
  audit in existing Ledger transaction. State survives connection reopen. No token
  requests, OAuth endpoints, client secrets or private key provisioning added.
- Existing gmail_sync retains encrypted table/history/cursor semantics; no second
  database/ledger, isolation-level replacement or historical data rewrite.

The new pending table is additive, created only when the primitive is instantiated.
OAuth start requires an authenticated owner-session identifier from a trusted app;
this primitive cannot itself prove that arbitrary caller input represents a login.
Both start and callback remain UNMOUNTED until HTTPS/Access/session and CSRF gates.
Successful state consumption is not AUTHORIZED or LIVE_VERIFIED. Interrupted token
exchange will require a new start rather than replaying a consumed state.

Integration regression:242run/240pass/2optional web dependency skips. Added tests:
policy denial before client, wrong session, replay, PKCE, strict expiry, STOP,
changed binding, reopened ledger and audit-failure rollback of state consumption.
Original ciphertext+cursor+audit rollback tests remain. First implementation run
hit4 identifier-length errors; prefixes corrected to existing80character contract,
then full suite passed. No tests weakened. No real Google data, OAuth consent,
provisioning, external writes, paid calls or deployment occurred. API spendGBP0.

Not integrated:reference Store,requests transport,token exchange/refresh,Drive,
Calendar,People,Tasks,Photos ingestion and graph. They require current official
API/security review and adaptation into single-ledger/page-atomic contracts.
Precise next increment: guarded Google read-only transport using existing pinned
TLS/public DNS primitives, then audited encrypted token lifecycle and SENT probe.
Production Google client/key store and owner consent remain external gates;
metadata acceptance must separately testprofile,SENT,message,thread,INBOX/ALL,
history. Bounded pilot is not full backfill. Existing host/DNS/Cloudflare gates
remain independent and were not re-diagnosed. No UI/provider status promoted.

Rollback code commit only; retain encrypted historical table/journal. New pending
state table can remain dormant. Revoke outstanding pending authorizations via a
reviewed operation before rotating encryption keys; never regenerate keys on restart.
