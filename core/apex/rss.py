"""Read public arXiv RSS 2.0 and Atom API feeds as untrusted data.

No model calls, payments, publishing, or user-account permissions.
"""
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

ATOM_NS = '{http://www.w3.org/2005/Atom}'
SOURCES = {
    'arxiv-ai': 'https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending',
    'arxiv-ml': 'https://export.arxiv.org/api/query?search_query=cat:cs.LG&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending',
}
ALLOWED_HOSTS = {'arxiv.org', 'export.arxiv.org', 'www.arxiv.org'}


def allowed_link(url):
    try:
        p = urlparse(url.strip())
        return (p.scheme == 'https' and p.hostname in ALLOWED_HOSTS
                and not p.username and not p.password and p.port in (None, 443)
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
