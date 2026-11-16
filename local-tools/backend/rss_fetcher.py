"""Read public arXiv and MIT News RSS/Atom feeds as untrusted data - no model call, no
account, no payment, free. Extracted from the parent project's rss.py (verified-working feed
URLs kept as-is) plus a plain stdlib HTTPS GET, simplified from the parent's pinned-DNS
transport since a personal local tool doesn't need that extra hardening layer.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

ATOM_NS = "{http://www.w3.org/2005/Atom}"
SOURCES = {
    "arxiv-ai": "https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending",
    "arxiv-ml": "https://export.arxiv.org/api/query?search_query=cat:cs.LG&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending",
    "mit-ai-news": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
}
ALLOWED_HOSTS = {"arxiv.org", "export.arxiv.org", "www.arxiv.org", "news.mit.edu"}
MAX_FEED_BYTES = 2_097_152


class RssFetchError(RuntimeError):
    pass


def allowed_link(url: str) -> bool:
    if not isinstance(url, str) or len(url) > 2000 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        return False
    try:
        p = urlparse(url)
        return (p.scheme == "https" and p.hostname in ALLOWED_HOSTS and p.username is None
                and p.password is None and p.port in (None, 443) and not p.fragment)
    except (ValueError, AttributeError, TypeError):
        return False


def _canonical_atom_url(raw_url: str):
    try:
        p = urlparse(raw_url.strip())
        if (p.scheme not in {"http", "https"} or p.hostname not in ALLOWED_HOSTS or p.username
                or p.password or p.port not in (None, 80, 443) or not p.path.startswith("/abs/")
                or p.query or p.fragment):
            return None
        candidate = "https://arxiv.org" + p.path
        return candidate if allowed_link(candidate) else None
    except (ValueError, AttributeError, TypeError):
        return None


def extract_items(raw: bytes, limit: int = 10) -> list:
    if not isinstance(raw, bytes) or len(raw) > MAX_FEED_BYTES:
        raise ValueError("Feed must be bytes within the size limit")
    if b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Feed declarations and NUL bytes are not permitted")
    root = ET.fromstring(raw)
    results = []
    if root.tag == ATOM_NS + "feed":
        for item in root.findall(ATOM_NS + "entry"):
            title = " ".join((item.findtext(ATOM_NS + "title") or "").split())
            url = _canonical_atom_url(item.findtext(ATOM_NS + "id") or "")
            if title and url:
                results.append({"title": title[:300], "link": url})
            if len(results) >= limit:
                break
    else:
        for item in root.findall(".//item"):
            title = " ".join((item.findtext("title") or "").split())
            link = (item.findtext("link") or "").strip()
            if title and allowed_link(link):
                results.append({"title": title[:300], "link": link})
            if len(results) >= limit:
                break
    return results


def fetch(url: str) -> bytes:
    if not allowed_link(url) and url not in SOURCES.values():
        raise RssFetchError("URL is outside the allowlisted feed hosts")
    req = urllib.request.Request(url, headers={"User-Agent": "local-tools-rss/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read(MAX_FEED_BYTES + 1)
    except urllib.error.URLError as exc:
        raise RssFetchError(f"Could not reach {url}: {exc}") from None


def latest_titles(limit: int = 10) -> list:
    out = []
    for name, url in SOURCES.items():
        try:
            for item in extract_items(fetch(url), limit=limit):
                out.append({**item, "feed": name})
        except Exception:
            continue  # a dead/blocked feed is evidence of nothing, not a crash
    return out
