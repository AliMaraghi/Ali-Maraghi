# PubMed search + retrieval (core/apex/pubmed.py) - TESTS_NOT_RUN, NOT_CONNECTED
Compiled only; never run against NCBI. Research aid, not clinical advice.

## Provenance of every detail
- VERIFIED from fetchable official NLM pages (2026-11-12): NLM Data Guide (base URL `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`; `esearch.fcgi`, `efetch.fcgi`; params db/term/id/retmax/retstart/retmode/rettype;
  PubMed XML = retmode xml + rettype abstract; ESearch up to 100,000 and EFetch up to 10,000 per request; "do not post more than three URL requests per second"; `tool` and `email` recommended) and an Archive-It capture of NLM's
  element descriptions (PMID, ArticleTitle, Abstract/AbstractText, ArticleDate, PubDate/MedlineDate, DateRevised, PublicationType "Retracted Publication", CommentsCorrections RetractionIn/RetractionOf).
- OWNER-SUPPLIED 2026-11-12 (used as instructed, not independently verified): ESearch `sort` (pub_date|relevance), `datetype=pdat` + `mindate`/`maxdate`, `usehistory=y` returning `WebEnv` and `query_key`, EFetch by WebEnv+query_key,
  `api_key` allowing 10 requests/second. The owner's base URL "https://nih.gov" was NOT used (not the E-utilities host; the Data Guide confirms the eutils host above).
- NOT verified from any fetched page: ESearch JSON field names. `search()` reads `esearchresult.{count, idlist, webenv, querykey}` from general knowledge and fails closed (INVALID_RESPONSE) if the shape differs.
- The NCBI Bookshelf pages (NBK25497/NBK25499) were blocked by a browser-check interstitial and were not scraped, as instructed.

## Behaviour
`build_search_path` (term <=500 chars, retmax 1..10,000, retstart, sort, mindate/maxdate YYYY[/MM[/DD]], usehistory), `build_fetch_path` (explicit PMIDs <=200 OR WebEnv+query_key with retstart/retmax <=200; always XML abstract),
`search` (JSON; returns count, pmids, webenv, query_key), `fetch_records` (XML; rejects `<!ENTITY`, 5 MB cap; reports `missing_pmids`; title/abstract wrapped as untrusted data; retraction status from PublicationType and RetractionIn/RetractionOf),
`RateLimiter`/`limiter_for` (>=0.34 s, or 0.11 s with an api_key), every request GET. `tool` defaults to "apex-research". `email` is sent only if the caller passes it from private configuration (none is defaulted or embedded);
`api_key` is a credential: never in errors or logs (transport failures are collapsed to TRANSPORT_ERROR). Runtime: none; no key or contact email is configured.
