"""Public-source poller. No LLM calls, spending or private account access."""
import os, time, urllib.request, logging
from .rss import SOURCES, extract_items
from .storage import ensure_schema, upsert

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('apex.monitor')

def poll_once():
    for name,url in SOURCES.items():
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"ApexPrivateResearchPrototype/0.1 (public RSS only)"})
            with urllib.request.urlopen(req,timeout=12) as response:
                # Basic size limit: 2 MiB per response
                raw=response.read(2_097_153)
            if len(raw)>2_097_152: raise ValueError('feed too large')
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
