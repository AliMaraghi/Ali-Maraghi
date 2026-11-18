"""Read public arXiv and university-news RSS 2.0 / Atom feeds as untrusted data.

No model calls, payments, publishing, or user-account permissions.

'mit-ai-news' verified live on 2026-11-13 (WebFetch): https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml
is real RSS 2.0, channel "MIT News - Artificial intelligence". Oxford (ox.ac.uk) and Stanford
(news.stanford.edu) candidate URLs were checked the same way and both returned HTTP 403 - not
added here rather than guessed; add a real, individually-verified URL (and matching hostname
below) if/when one is confirmed working.
"""
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

ATOM_NS = '{http://www.w3.org/2005/Atom}'
SOURCES = {
    'arxiv-ai': 'https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending',
    'arxiv-ml': 'https://export.arxiv.org/api/query?search_query=cat:cs.LG&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending',
    'mit-ai-news': 'https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml',
    # ScienceDaily: RSS 2.0, listed on its own newsfeeds page (sciencedaily.com/newsfeeds.htm) and
    # seen as real feed XML via web search on 2026-11-18. NOT yet fetched live from the VPS.
    'sciencedaily-science': 'https://www.sciencedaily.com/rss/top/science.xml',
    'sciencedaily-technology': 'https://www.sciencedaily.com/rss/top/technology.xml',
}
ALLOWED_HOSTS = {'arxiv.org', 'export.arxiv.org', 'www.arxiv.org', 'news.mit.edu', 'www.sciencedaily.com'}
MAX_FEED_BYTES = 2_097_152


def allowed_link(url):
    if (not isinstance(url, str) or len(url) > 2000
            or any(ord(char) < 33 or ord(char) == 127 for char in url)):
        return False
    try:
        p = urlparse(url)
        return (p.scheme == 'https' and p.hostname in ALLOWED_HOSTS
                and p.username is None and p.password is None and p.port in (None, 443)
                and not p.fragment and len(url) <= 2000)
    except (ValueError, AttributeError, TypeError):
        return False


def _canonical_atom_url(raw_url):
    """arXiv Atom IDs commonly start with HTTP; canonicalize *trusted IDs* only."""
    try:
        p = urlparse(raw_url.strip())
        if (p.scheme not in {'http', 'https'} or p.hostname not in ALLOWED_HOSTS
                or p.username or p.password or p.port not in (None, 80, 443)
                or not p.path.startswith('/abs/') or p.query or p.fragment):
            return None
        candidate = 'https://arxiv.org' + p.path
        return candidate if allowed_link(candidate) else None
    except (ValueError, AttributeError, TypeError):
        return None


def extract_items(raw, limit=30):
    if not isinstance(raw, bytes) or len(raw) > MAX_FEED_BYTES:
        raise ValueError('Feed must be bytes within the size limit')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('Item limit must be an integer from 1 to 1000')
    # Public RSS/Atom does not need DTDs or custom entities. Reject them before
    # XML parsing, including UTF-16/32 encodings that could hide declarations.
    if b'\x00' in raw or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Feed declarations and NUL bytes are not permitted')
    root = ET.fromstring(raw)
    results = []
    if root.tag == ATOM_NS + 'feed':
        for item in root.findall(ATOM_NS + 'entry'):
            title = ' '.join((item.findtext(ATOM_NS + 'title') or '').split())
            # Entry ID is canonical arXiv identifier. Ignore external links.
            url = _canonical_atom_url(item.findtext(ATOM_NS + 'id') or '')
            if title and url:
                results.append((title[:300], url))
            if len(results) >= limit:
                break
    else:
        for item in root.findall('.//item'):
            title = ' '.join((item.findtext('title') or '').split())
            link = (item.findtext('link') or '').strip()
            if title and allowed_link(link):
                results.append((title[:300], link))
            if len(results) >= limit:
                break
    return results
