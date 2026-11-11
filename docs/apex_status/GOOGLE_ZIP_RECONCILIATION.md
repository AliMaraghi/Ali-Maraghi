# apex-google.zip verified against current APEX

Archive: /home/apexdev/.codex/attachments/8b916064-8470-4392-b0fd-c9ee283d4c33/apex-google.zip
SHA256: d37fd703065f4642bfbcb37afd93dd328fae3cfa2d7c8e360e87e0b68c9137fe
Entry HEAD:3ee97308100c8e8a61d7ed3458332bc840ff2f96
Branch:apex/unified-field-integration

ZIP exists; CRC test passed.12regular safe members,54645uncompressed bytes;
all11listed internal checksums matched. Fresh extraction into ignored temporary
review directory work/review-kit/google-zip-5y6swfok; no installer hooks executed.
Every member is byte-for-byte identical to the previously reviewed rebuilt addon.
The attached tar.gz contains identical file bytes too (SHA256 recorded in inventory).
New compression changes archive hash, not source code. All12files were compared
through exact identity with fully reviewed prior contents and mapped individually
to currentHEAD. Mapped working source files exactly equal their committed versions.
Detailed mappings/hashes:google_zip_20261111_head_comparison.json.

No new runtime source imported; no pending package code delta exists. Compatible
adaptations already committed in3ee9730 remain:
core/apex/google_policy.py, core/apex/google_oauth_state.py,
core/apex/gmail_sync.py and their tests. They preserve explicit import review,
metadata minimization, session/client/owner/redirect-bound PKCE state, STOP and
existing atomic Ledger. core/apex/kernel/memory.py BEGIN IMMEDIATE/SAVEPOINT
implementation unchanged. No second SQLite database or reference audit imported.

Previously reproduced conflicts remain resolved by exclusion/adaptation:
reference token save is not atomic with audit; metadata helpers request full content;
reference transport lacks existing pinned DNS/TLS controls; state lacks owner-session
binding; other-service pagination/atomicity incomplete. See GOOGLE_ADDON_INTEGRATION.md
and google_addon_adverse_probes.json. Exact same bytes do not justify reintroducing them.
Instructions inside attached docs remain reference, not new user authority.

Requested regression executed against this state:
-242project tests run:240passed,2optional web dependency skips,0failures/errors.
-26reference tests passed using this exact extraction, no Google requests.
-11deployment bundle tests passed; no deployment executed.
These suites are separate, not275live integration tests. Originals18roles/fourplanes/
130target unchanged. Canonical manifesto SHA256 remains
3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd.

Still blocked/unimplemented: production Google OAuth client/secure key binding and
owner consent; authenticated Google transport, atomic credential refresh/token broker;
private-source confidentiality/retention/deletion review; actual SENT/profile/message/
thread/history acceptance; Drive/Calendar/People/Tasks review. OAuth primitives remain
unmounted. Host administration, owner-only Cloudflare Access/DNS/HTTPS and independent
VPS liveness remain separate open gates. No private data imported, credentials created,
new API spend, live Google result or production change. This commit records review and
regression evidence only, not a new implementation or live integration.
