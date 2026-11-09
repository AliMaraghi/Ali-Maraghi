"""Public-source poller. No LLM calls, spending or private account access."""
import os, time, urllib.request, logging
from .rss import SOURCES, extract_items, allowed_link, MAX_FEED_BYTES
from .storage import ensure_schema, upsert

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('apex.monitor')

FETCH_TIMEOUT_SECONDS = 12


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A public feed must never redirect a request to another destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Feed redirects are disabled")


def fetch_feed(url):
    """Bound bytes and socket waits; reject redirects and elapsed slow feeds.

    The elapsed deadline is checked between read1 calls; an in-progress socket
    operation can still take up to the socket timeout. This is not an OS-level
    strict wall-clock deadline.
    """
    if not allowed_link(url):
        raise ValueError("Feed URL is not allowlisted")
    deadline = time.monotonic() + FETCH_TIMEOUT_SECONDS
    req = urllib.request.Request(
        url, headers={"User-Agent": "ApexPrivateResearchPrototype/0.1 (public RSS only)"},
    )
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=FETCH_TIMEOUT_SECONDS) as response:
        chunks = []
        size = 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Feed elapsed-time limit exceeded")
            # read1 makes at most one underlying buffered read, allowing the
            # elapsed guard to run even when a server trickles response bytes.
            chunk = response.read1(min(65536, MAX_FEED_BYTES + 1 - size))
            if not chunk:
                return b"".join(chunks)
            size += len(chunk)
            if size > MAX_FEED_BYTES:
                raise ValueError("Feed size limit exceeded")
            chunks.append(chunk)

def poll_once():
    for name,url in SOURCES.items():
        try:
            raw=fetch_feed(url)
            parsed=extract_items(raw)
            for title,link in parsed: upsert(name,title,link)
            log.info('source=%s items=%s',name,len(parsed))
        except Exception as exc:
            log.warning('source=%s failed: %s',name,type(exc).__name__)

def main():
    if os.getenv('APEX_MONITOR_ENABLED','true').lower()!='true':
        log.info('monitor disabled'); return
    interval=max(900,int(os.getenv('APEX_MONITOR_INTERVAL_SECONDS','21600')))
    while True:
        try:
            ensure_schema(); poll_once()
        except Exception as exc:
            log.warning('poll cycle failed: %s', type(exc).__name__)
        time.sleep(interval)

if __name__=='__main__':main()
