# Contracts Finder adapter — tested offline, live packet blocked

Files: core/apex/sources/contracts_finder.py; scripts/collect_public_source.py;
tests/test_public_source.py. Fixed anonymous GET host/path:
`https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search`.
No accounts, secrets, contact/bid actions, subscriptions or paid API calls.

Official sources consulted on 2026-11-10:

- https://www.gov.uk/government/publications/open-contracting (page last updated
  2021): identifies the public OCDS API and links its guide. GOV.UK footer states
  OGL with exceptions; that is not independent verification of all endpoint data.
- https://assets.publishing.service.gov.uk/media/5e99b67dd3bf7f0318cff3b8/Guide-to-Open-Contracting-Data-Standard-implementation-on-Contracts-Finder-V.2.1.pdf
  (older publication): documents GET, date/size/page parameters, default100 records,
  and open/closed/awarded stages. The parameter table and example GET body leave
  current request encoding to be confirmed. No current procurement-law advice is
  inferred from old thresholds in that document.
- Live Contracts Finder documentation and the National Archives OGL page returned
  HTTP403 through the browsing tool. No login, browser impersonation or bypass was
  attempted. Current endpoint licence verification remains pending and is explicitly
  false in output; attribution is proposed, not a compliance certification.

## Bounds and transport

Explicit `--fetch-public`; all other modes perform no retrieval. Date window<=31
days, requested page1/size5, fixed query fields, at most one same-host/path/scope
redirect and no automatic retries. Every DNS answer must be global unicast;
mixed private/public, mapped/private/link-local/loopback answers are rejected.
The socket connects to a validated numeric address, checks its peer, and validates
TLS against the original hostname. No second DNS lookup during connect. Redirects
repeat address validation. Proxy environment/cookies/credentials are not inherited.

JSON body<=1MiB; compression/HTML/invalid length/oversize fail closed. Child-process
timeout15s bounds DNS, TLS, headers and body together; individual socket timeout5s.
Python http.client's own finite header bounds apply (not a1MiB header budget).
Response errors are redacted to developer-defined codes. Tests use mocked network
responses; TLS context checks and one real endpoint attempt do not constitute an
independent network penetration test or production egress firewall.

## Actual observations

Two manual invocations were made after a sandbox network grant, for publication
dates2026-11-09 through2026-11-10. First saved only a generic parse failure. A second
diagnostic invocation, after improving fixed error messages, reported:
`Server exceeded requested page size`.

Reports: public_source_live_attempt.json and public_source_diagnostic_attempt.json.
The response reached the client's JSON/page-size validator; no usable notice packet
was accepted. HTTP-hop counts were not persisted for rejected packets; each invocation
was bounded to two GETs, but the actual count is not asserted. No third request was
made and no pagination/size gate was weakened. Raw notices/contact details were not
retained. The failure receipt itself is real local operational evidence and feeds
the durable diagnostic workflow; it is not evidence of an economic opportunity.

## Exact executable integration prerequisites

1. Obtain the current authoritative request encoding for size/page/date filters
   (query parameters versus the documented structured GET body). Do not guess new
   parameters or silently increase collection size to turn failure into a pass.
2. Verify current source terms/licence and permitted retention, including exclusions
   for third-party/personal content. No publication is authorized by this task.
3. Add an exact sanitized response-schema contract fixture and test date, identity,
   count, stage and deadline semantics. Current parser accepts only the documented
   flat release shape; version drift must fail explicitly.
4. After any required sandbox network grant, run one bounded documented request:

```
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/collect_public_source.py --fetch-public --from-date 2026-11-09 --to-date 2026-11-10
```

5. Require a usable minimally retained packet with actual request timestamps,
   byte digest, scope and adverse status/deadline flags before admitting source
   observations to market research. Even a valid packet is one non-independent
   registry page; it proves neither founder eligibility nor customer demand.

Do not reuse the source URL's self-declared metadata as independent verification.
The adapter's retained notice IDs/dates/status are minimized, not a complete archive;
discarding raw bodies limits later independent reproduction and must remain visible.
