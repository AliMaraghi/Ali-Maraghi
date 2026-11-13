"""PubMed search and retrieval (NCBI E-utilities ESearch + EFetch, db=pubmed). Read-only research aid. Status: TESTS_NOT_RUN, NOT_CONNECTED.

Sources and provenance (2026-11-12):
- VERIFIED from NLM Data Guide https://www.nlm.nih.gov/dataguide/eutilities/utilities.html: base URL https://eutils.ncbi.nlm.nih.gov/entrez/eutils/, endpoints esearch.fcgi / efetch.fcgi, params db, term, id,
  retmax, retstart, retmode, rettype; PubMed XML (retmode=xml, rettype=abstract) valid for EFetch; "do not post more than three URL requests per second"; `tool` and `email` recommended.
  The owner's message named the base URL "https://nih.gov"; that is not the E-utilities host and was NOT used.
- VERIFIED element meanings (NLM element descriptions, Archive-It capture): PubmedArticle > MedlineCitation > PMID, DateRevised, Article (ArticleTitle, Abstract/AbstractText, ArticleDate), PubDate/MedlineDate,
  PublicationType "Retracted Publication", CommentsCorrections RefType RetractionIn / RetractionOf.
- OWNER-SUPPLIED (2026-11-12, not verified from a fetchable official page): ESearch parameters sort (pub_date|relevance), datetype=pdat with mindate/maxdate, usehistory=y returning WebEnv and query_key, EFetch by
  WebEnv+query_key, `api_key` raising the limit to 10 requests per second. retmax is capped here at 10,000 (the Data Guide says ESearch may return up to 100,000 per URL).
- NOT verified from any fetched page: the JSON field names of ESearch output. `search()` parses `esearchresult.{count, idlist, webenv, querykey}` from general knowledge of NCBI's JSON output and
  fails closed with INVALID_RESPONSE if the structure differs. Exact nesting of PubDate/CommentsCorrections is handled by descendant search.
Privacy: `email` is sent only if the caller passes it from private configuration; nothing here supplies a default address. `api_key` is a credential: it appears only in the request query, never in errors.
Titles and abstracts are external text, wrapped as untrusted data, never instructions. Research aid, not clinical advice. EFetch is parsed for retmode=xml only.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from .agent_contract import wrap_untrusted

HOST = "eutils.ncbi.nlm.nih.gov"
SEARCH_PATH = "/entrez/eutils/esearch.fcgi"
FETCH_PATH = "/entrez/eutils/efetch.fcgi"
MAX_IDS = 200                      # conservative: documented EFetch cap is 10,000 per request
MAX_RETMAX = 10_000
LIMIT = 5_000_000
MIN_INTERVAL = 0.34                # <= 3 requests per second without an api_key
MIN_INTERVAL_KEYED = 0.11          # <= 10 per second with an api_key (owner-supplied, unverified)
PMID = re.compile(r"[1-9]\d{0,7}")
TOOL = re.compile(r"[A-Za-z0-9_.-]{1,40}")
EMAIL = re.compile(r"[^@\s,;<>()\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
API_KEY = re.compile(r"[A-Za-z0-9]{20,64}")
WEBENV = re.compile(r"[A-Za-z0-9_.~-]{10,300}")
QUERY_KEY = re.compile(r"[1-9]\d{0,5}")
DATE_PARAM = re.compile(r"\d{4}(?:/\d{2}(?:/\d{2})?)?")
SORTS = ("pub_date", "relevance")


class PubMedError(RuntimeError):
    pass


class RateLimiter:
    """Enforces minimum spacing between requests; clock and sleep are injectable."""

    def __init__(self, clock=time.monotonic, sleep=time.sleep, interval=MIN_INTERVAL):
        self.clock, self.sleep, self.interval, self.last = clock, sleep, interval, None

    def wait(self):
        now = self.clock()
        if self.last is not None and now - self.last < self.interval:
            self.sleep(self.interval - (now - self.last))
            now = self.clock()
        self.last = now


def limiter_for(api_key, clock=time.monotonic, sleep=time.sleep):
    return RateLimiter(clock, sleep, MIN_INTERVAL_KEYED if api_key else MIN_INTERVAL)


def _identity(query, tool, email, api_key):
    if not isinstance(tool, str) or not TOOL.fullmatch(tool):
        raise ValueError("Invalid tool name")
    query["tool"] = tool
    if email is not None:
        if not isinstance(email, str) or not EMAIL.fullmatch(email):
            raise ValueError("Invalid email")
        query["email"] = email
    if api_key is not None:
        if not isinstance(api_key, str) or not API_KEY.fullmatch(api_key):
            raise ValueError("Invalid api_key")
        query["api_key"] = api_key


def build_search_path(term, retmax=20, retstart=0, sort=None, mindate=None, maxdate=None, usehistory=False,
                      tool="apex-research", email=None, api_key=None):
    if not isinstance(term, str) or not 1 <= len(term) <= 500 or any(ord(c) < 32 or ord(c) == 127 for c in term):
        raise ValueError("term must be 1..500 printable characters")
    if type(retmax) is not int or not 1 <= retmax <= MAX_RETMAX or type(retstart) is not int or not 0 <= retstart <= 10**7:
        raise ValueError("Invalid retmax/retstart")
    query = {"db": "pubmed", "term": term, "retmode": "json", "retmax": retmax, "retstart": retstart}
    if sort is not None:
        if sort not in SORTS:
            raise ValueError("sort must be pub_date or relevance")
        query["sort"] = sort
    if (mindate is None) != (maxdate is None):
        raise ValueError("mindate and maxdate go together")
    if mindate is not None:
        if not all(isinstance(v, str) and DATE_PARAM.fullmatch(v) for v in (mindate, maxdate)):
            raise ValueError("Dates must be YYYY, YYYY/MM or YYYY/MM/DD")
        query.update(datetype="pdat", mindate=mindate, maxdate=maxdate)
    if usehistory:
        query["usehistory"] = "y"
    _identity(query, tool, email, api_key)
    return SEARCH_PATH + "?" + urlencode(query)


def build_fetch_path(pmids=None, webenv=None, query_key=None, retstart=0, retmax=None,
                     tool="apex-research", email=None, api_key=None):
    """EFetch by explicit PMIDs OR by WebEnv+query_key from a usehistory search; always XML abstract records."""
    by_ids, by_history = pmids is not None, webenv is not None or query_key is not None
    if by_ids == by_history:
        raise ValueError("Use either pmids or webenv+query_key")
    query = {"db": "pubmed", "retmode": "xml", "rettype": "abstract"}
    if by_ids:
        if not isinstance(pmids, (list, tuple)) or not 1 <= len(pmids) <= MAX_IDS or not all(isinstance(p, str) and PMID.fullmatch(p) for p in pmids):
            raise ValueError("1..200 PMIDs (digits, no leading zero) required")
        query["id"] = ",".join(pmids)
    else:
        if not (isinstance(webenv, str) and WEBENV.fullmatch(webenv) and isinstance(query_key, str) and QUERY_KEY.fullmatch(query_key)):
            raise ValueError("Valid webenv and query_key required")
        if type(retstart) is not int or not 0 <= retstart <= 10**7 or type(retmax) is not int or not 1 <= retmax <= MAX_IDS:
            raise ValueError("History fetch needs retstart >= 0 and 1 <= retmax <= 200")
        query.update(WebEnv=webenv, query_key=query_key, retstart=retstart, retmax=retmax)
    _identity(query, tool, email, api_key)
    return FETCH_PATH + "?" + urlencode(query)


def _call(path, transport, limiter, accept):
    limiter.wait()
    try:
        status, content_type, raw = transport("GET", path, {"Accept": accept, "Accept-Encoding": "identity"})
    except Exception:
        raise PubMedError("TRANSPORT_ERROR") from None            # transport errors can embed the URL (and api_key)
    if status != 200:
        raise PubMedError(f"PUBMED_HTTP_{int(status)}")
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > LIMIT or not isinstance(content_type, str):
        raise PubMedError("INVALID_RESPONSE")
    return content_type.lower(), bytes(raw)


def search(term, transport, limiter, retmax=20, retstart=0, sort=None, mindate=None, maxdate=None, usehistory=False,
           tool="apex-research", email=None, api_key=None):
    """ESearch (JSON). Returns {count, pmids, webenv, query_key}; webenv/query_key are None unless usehistory was requested."""
    path = build_search_path(term, retmax, retstart, sort, mindate, maxdate, usehistory, tool, email, api_key)
    content_type, raw = _call(path, transport, limiter, "application/json")
    if "json" not in content_type:
        raise PubMedError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        result = strict_json(raw.decode())["esearchresult"]
        ids, count = result["idlist"], int(result["count"])
        if not isinstance(ids, list) or not all(isinstance(i, str) and PMID.fullmatch(i) for i in ids) or len(ids) > retmax or count < 0:
            raise ValueError("shape")
        webenv, key = result.get("webenv"), result.get("querykey")
        if usehistory and not (isinstance(webenv, str) and WEBENV.fullmatch(webenv) and isinstance(key, str) and QUERY_KEY.fullmatch(key)):
            raise ValueError("history")
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PubMedError("INVALID_RESPONSE") from None
    return {"count": count, "pmids": ids, "webenv": webenv if usehistory else None, "query_key": key if usehistory else None}


def _text(node):
    return " ".join("".join(node.itertext()).split()) if node is not None else None


def _date(node):
    if node is None:
        return None
    parts = [_text(node.find(tag)) for tag in ("Year", "Month", "Day")]
    if parts[0]:
        return "-".join(p for p in parts if p)
    return _text(node.find("MedlineDate"))


def parse_efetch_xml(raw, retrieved_on):
    """Parse EFetch PubMed XML into records. `retrieved_on` (YYYY-MM-DD) is supplied by the caller (no clock read)."""
    if not isinstance(retrieved_on, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved_on):
        raise ValueError("retrieved_on must be YYYY-MM-DD")
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > LIMIT or b"<!ENTITY" in raw:
        raise PubMedError("INVALID_RESPONSE")
    try:
        root = ET.fromstring(bytes(raw))
    except ET.ParseError:
        raise PubMedError("INVALID_RESPONSE") from None
    out = []
    for article in root.iter("PubmedArticle"):
        citation = article.find("MedlineCitation")
        pmid = _text(citation.find("PMID")) if citation is not None else None
        if not pmid or not PMID.fullmatch(pmid):
            raise PubMedError("INVALID_RESPONSE")
        abstract = []
        for part in citation.iter("AbstractText"):
            label = part.get("Label")
            abstract.append((label + ": " if label else "") + (_text(part) or ""))
        types = [_text(t) for t in citation.iter("PublicationType") if _text(t)]
        refs = {"RetractionIn": [], "RetractionOf": []}
        for item in citation.iter("CommentsCorrections"):
            kind = item.get("RefType")
            if kind in refs:
                ref = _text(item.find("PMID"))
                refs[kind].append(ref if ref and PMID.fullmatch(ref) else None)
        out.append({
            "pmid": pmid,
            "title": wrap_untrusted("web", _text(citation.find(".//ArticleTitle")) or ""),
            "abstract": wrap_untrusted("web", "\n".join(abstract)),
            "article_date": _date(citation.find(".//ArticleDate")), "pub_date": _date(citation.find(".//PubDate")),
            "date_revised": _date(citation.find("DateRevised")),
            "publication_types": types,
            "retraction": {"retracted_publication_type": "Retracted Publication" in types,
                           "retraction_in": refs["RetractionIn"], "retraction_of": refs["RetractionOf"]},
            "source": "pubmed-efetch", "retrieved_on": retrieved_on})
    return out


def fetch_records(retrieved_on, transport, limiter, pmids=None, webenv=None, query_key=None, retstart=0, retmax=None,
                  tool="apex-research", email=None, api_key=None):
    """EFetch (XML). Returns {records, missing_pmids}; `missing_pmids` is only computed for an explicit PMID list."""
    path = build_fetch_path(pmids, webenv, query_key, retstart, retmax, tool, email, api_key)
    content_type, raw = _call(path, transport, limiter, "text/xml, application/xml")
    if "xml" not in content_type:
        raise PubMedError("INVALID_RESPONSE")
    records = parse_efetch_xml(raw, retrieved_on)
    missing = sorted(set(pmids) - {r["pmid"] for r in records}) if pmids is not None else []
    return {"records": records, "missing_pmids": missing}


def live_transport(method, path, headers):                      # pragma: no cover - not exercised offline
    if method != "GET":
        raise ValueError("Only GET is permitted")
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, None, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()
