# Outlook / Microsoft Graph adapter (TESTS_NOT_RUN, never run live)
Module: core/apex/outlook_graph.py. Compiles only. No send function exists and no delete.

Verified (learn.microsoft.com, graph-rest-1.0, fetched 2026-11-12):
- https://learn.microsoft.com/en-us/graph/api/user-post-messages : POST /me/messages creates a draft in Drafts; delegated permission Mail.ReadWrite; JSON body subject, body{contentType,content}, toRecipients[].emailAddress.address; 201 Created; response has isDraft and id. Sending is a separate operation (not implemented).
- https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messages : GET /me/mailFolders/{id}/messages; least-privileged delegated Mail.ReadBasic, higher Mail.ReadWrite/Mail.Read; 200 with `value`; OData query parameters supported.
Not verified from the fetched pages (used as general Graph/OData convention, risk acknowledged): the `$select` and `$top` values, `from.emailAddress.address` shape in the list response, folder well-known names, paging via @odata.nextLink (not implemented, one page max 50). Scope-name strings in assert_scopes are lower-cased and the per-scope check for send-capable names ("mail.send", any name containing "send") is a conservative guard, not a Microsoft-documented list.
Note: Mail.ReadWrite is needed for draft creation; it is broader than read-only. Token acquisition (OAuth) is not implemented.
Behaviour: token None -> NOT_CONFIGURED; host fixed graph.microsoft.com; upstream bodies never surfaced; list returns id, receivedDateTime, from, subject (redacted, <=120 chars, wrapped as untrusted "email" data); folder ids must be allow-listed. redact_sensitive is heuristic.


## Update 2026-11-12 (lead): paging and field gaps closed from official pages - TESTS_NOT_RUN
- Verified (learn.microsoft.com/graph/paging): `@odata.nextLink` is returned while more pages exist; the ENTIRE URL must be used as-is; `$skiptoken`/`$skip`
  are opaque and must not be extracted; follow until the property is absent; pages may hold zero or more items; a requested `$top` may be ignored or rejected.
- Verified (message resource, v1.0): `id`, `subject`, `receivedDateTime`, `from` (a `recipient`, whose property is `emailAddress`) exist; `$select` is documented for messages.
- Implemented: explicit `$select=id,receivedDateTime,from,subject` plus `$top` on the first request only; later requests use the validated nextLink path+query verbatim.
  `_next_path` forwards the credential only for https, host `graph.microsoft.com`, no port/userinfo/fragment, a query present, and exactly the allow-listed
  folder's `/v1.0/me/mailFolders/{id}/messages` (compared percent-decoded, forwarded unchanged). Anything else raises `INVALID_NEXT_LINK`.
  Bounds: 10 pages, 200 items; `list_headers` now returns `{"headers", "pages", "truncated"}`.
- Draft creation keeps `Mail.ReadWrite`; the module still has no send function and refuses any send-capable scope (no-send preserved).
- Still unconfirmed: the `emailAddress` sub-property name `address` is from the create-message sample (not from the recipient/emailAddress pages fetched), and the
  maximum `$top` for this endpoint. Never run against the live service; no token exists. If Graph encodes folder ids differently in a nextLink the check fails closed.
