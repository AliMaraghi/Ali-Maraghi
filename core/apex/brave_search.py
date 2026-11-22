"""Web search through the official Brave Search API, limited to institutional domains.

One fixed endpoint (https://api.search.brave.com/res/v1/web/search), GET only, the owner's own
key from a private file. Each language's query carries a `site:` filter for that country's
public institutions, so results come from universities, government, health bodies and journals
rather than the open web. Only what the API returns (title, URL, snippet) is used - result
pages themselves are never fetched.

The API is metered: a monthly call ceiling is enforced here so a loop or a busy day cannot run
up a bill. Calls are spaced out because the API allows about one request a second.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode, urlsplit

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
KEY_SHAPE = re.compile(r"[A-Za-z0-9_-]{20,80}")
SYSTEM_KEY = Path("/etc/apex/brave-api-key")
MONTHLY_CEILING = 600                      # calls per calendar month, all languages together
PER_QUERY = 3
SPACING_SECONDS = 1.1
# language -> (search_lang sent to the API, site filter for that country's institutions)
REGIONS = {
    "en-gb": ("en", "site:gov.uk OR site:nhs.uk OR site:ac.uk OR site:bankofengland.co.uk OR site:bbc.co.uk"),
    "en-us": ("en", "site:nih.gov OR site:cdc.gov OR site:harvard.edu OR site:stanford.edu OR site:federalreserve.gov"),
    "global": ("en", "site:who.int OR site:nature.com OR site:oecd.org OR site:imf.org OR site:ieee.org"),
    "de": ("de", "site:bund.de OR site:rki.de OR site:mpg.de OR site:bundesbank.de"),
    "fr": ("fr", "site:gouv.fr OR site:has-sante.fr OR site:inserm.fr OR site:banque-france.fr"),
    "es": ("es", "site:gob.es OR site:csic.es OR site:bde.es"),
    "zh": ("zh-hans", "site:gov.cn OR site:edu.cn"),
    "ja": ("jp", "site:go.jp OR site:ac.jp"),
    "ko": ("ko", "site:go.kr OR site:ac.kr"),
    # Property portals: search-engine links only (the portals themselves are never fetched or scraped).
    "property": ("en", "site:rightmove.co.uk OR site:zoopla.co.uk OR site:onthemarket.com"),
    # Event listing sites: search-engine links only, the sites themselves are never fetched or scraped.
    "events": ("en", "site:ra.co OR site:designmynight.com OR site:eventbrite.co.uk OR site:dice.fm OR site:feverup.com"),
}
PHRASE_LANG = {"en-gb": "en", "en-us": "en", "global": "en"}


class BraveError(RuntimeError):
    pass


def _owner_file(root) -> Path:
    return Path(root) / "runtime" / "inbox" / "brave-api-key"


def load_key(root) -> str | None:
    for path in (SYSTEM_KEY, _owner_file(root)):
        try:
            if path.is_file() and not path.stat().st_mode & 0o077:
                value = path.read_text().strip()
                if KEY_SHAPE.fullmatch(value):
                    return value
        except OSError:
            continue
    return None


def save_key(root, key) -> None:
    if not isinstance(key, str) or not KEY_SHAPE.fullmatch(key.strip()):
        raise ValueError("Not a Brave Search API key")
    path = _owner_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w") as out:
        out.write(key.strip() + "\n")
    os.chmod(path, 0o600)


def _usage_file(root) -> Path:
    return Path(root) / "runtime" / "inbox" / "brave_usage.json"


def usage(root, now: float | None = None) -> dict:
    month = time.strftime("%Y-%m", time.gmtime(time.time() if now is None else now))
    try:
        data = json.loads(_usage_file(root).read_text())
    except (OSError, ValueError):
        data = {}
    return {"month": month, "calls": int(data.get(month, 0)) if isinstance(data, dict) else 0, "ceiling": MONTHLY_CEILING}


def _count(root, now: float) -> None:
    state = usage(root, now)
    if state["calls"] >= MONTHLY_CEILING:
        raise BraveError("MONTHLY_CEILING_REACHED")
    path = _usage_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({state["month"]: state["calls"] + 1}))
    os.chmod(path, 0o600)


def http_get(url: str, key: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key,
                                                   "User-Agent": "APEX-Research/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read(600_000)
    except urllib.error.HTTPError as exc:
        raise BraveError(f"HTTP_{exc.code}") from None        # never the response body, never the key
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BraveError(type(exc).__name__) from None


def search(root, key: str, region: str, phrase: str, get=http_get, now: float | None = None) -> list:
    """Up to three institutional results for one region: [{title, url, domain, lang, extract}]."""
    if region not in REGIONS:
        raise ValueError("Unknown region")
    now = time.time() if now is None else now
    search_lang, sites = REGIONS[region]
    _count(root, now)
    query = urlencode({"q": f"{phrase[:160]} ({sites})", "count": PER_QUERY, "search_lang": search_lang,
                       "safesearch": "moderate", "text_decorations": 0})
    data = json.loads(get(f"{ENDPOINT}?{query}", key))
    allowed = tuple(s.replace("site:", "") for s in sites.split(" OR "))
    out = []
    for item in ((data.get("web") or {}).get("results") or [])[:PER_QUERY]:
        url = item.get("url") if isinstance(item, dict) else None
        host = (urlsplit(url).hostname or "") if isinstance(url, str) and url.startswith("https://") else ""
        text = " ".join(re.sub(r"<[^>]+>", " ", str(item.get("description") or "")).split())[:500] if host else ""
        # The filter is enforced here too: a result outside the listed institutions is dropped.
        if host and text and any(host == d or host.endswith("." + d) for d in allowed):
            out.append({"title": " ".join(str(item.get("title") or "").split())[:140], "url": url[:500],
                        "domain": host, "lang": region, "extract": text})
    return out
