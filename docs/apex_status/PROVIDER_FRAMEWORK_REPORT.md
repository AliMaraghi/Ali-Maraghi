# Provider framework and live research connector

Entry d694959 on apex/unified-field-integration. Existing registry, databases,
FTS/TED adapters and historical traces retained. Founder inventory file is still
not recovered; this catalog is not presented as the authoritative130-provider list.

Implemented apex.providers.Provider immutable adapter contract, reviewed adapter
catalog, explicit connectors probe command, durable intent/result lineage, replay
without repeat retrieval, ambiguous-crash blocking and dashboard inventory projection.
Crossref is an additional research provider selected from the founder-approved
research category, not a falsely recovered founder inventory entry. Existing
procurement workflows continue unchanged. Catalog cannot grant arbitrary hosts,
credentials, paid budgets or actions. Other transport families, OAuth/banking broker,
credential renewal, generalized pagination and dynamic provider loading remain
NOT_IMPLEMENTED. No claim of universal connector completion.

Crossref official documentation reviewed:
https://www.crossref.org/documentation/retrieve-metadata/rest-api/
Public REST metadata access requires no account. This adapter selects only DOI,
title, publisher, type and URL; no abstracts, author records or full text. Source
metadata is not independent scientific validation. Publisher content rights are
not inferred from metadata access. One page, three records, zero retries, no paid
service, no contact identity supplied. No continuous polling was enabled.

Transport reuses reviewed HTTPS allowlist, public-IP validation, pinned destination,
TLS hostname verification, redirect restrictions,1MiB transport ceiling,20s hard
timeout; adapter further bounds normalized response to64KiB and three records.
Remote data remains data, never tool instructions. STOP is checked before durable
intent and before retrieval. The transaction holds through bounded retrieval;
stop latency is graceful, not instantaneous. Interrupted attempts are not silently
retried. Latest failure supersedes prior success in historical status projection.

ACTUAL LIVE RESULT: crossref-20261110-v1, HTTP200 at
2026-11-10T22:54:53.357996+00:00,3 metadata records, digest
34cd6fd6aede491345a469fb85ce5292aeb43a08baa2d0b104ba37a68c26b91d.
Exact request, IP hop, minimized raw response and records are in
reports/validation/crossref_live_receipt.json and existing runtime journal.
The journal now verifies79 events. Dashboard provider projection includes this
receipt; public dashboard publication is NOT verified. FTS/TED have prior live
receipts; Crossref is the only new live provider exchange in this increment.

Tests217 run /215 passed /2 optional web dependency skips /0 failures. New tests:
real local audit persistence and replay, conflicting trace identity, STOP preventing
network, interrupted retrieval preventing refetch, invalid digest/HTTP429 rejection,
unknown adapter and forbidden endpoint rejection. Fixtures are not counted as live.
Manifesto hash unchanged;178 trace groups/968 source units retained. No independent
utility superiority measured, no income and GBP0 paid API spend.

Deployment remains blocked by unavailable approved administrative execution path
and absent Cloudflare management/owner Access binding. No self-SSH sandbox bypass,
root installation, DNS mutation or unmanaged background service. Production server
packaging and remaining agent/provider implementations are still engineering work,
not falsely reclassified as external blockers.

Replay existing live receipt without network:
python3 -B scripts/apex connectors probe --provider crossref --query 'evidence based decision making' --trace crossref-20261110-v1
Inspect catalog and historical receipts:
python3 -B scripts/apex connectors verify
Next independent increment: normalize existing FTS/TED contracts into the same
adapter interface without changing their stronger field workflow and add bounded
capability-specific health expiry. No scheduled request until rate-policy reviewed.
Rollback code only; retain new intent/result events and historical evidence.
