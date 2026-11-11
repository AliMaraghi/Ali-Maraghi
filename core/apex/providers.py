"""Reviewed public provider adapter contract and durable explicit probe receipts.

Extensibility never grants arbitrary network access, credentials or paid spending.
The founder master inventory remains missing; this is an implementation catalog.
"""
from dataclasses import dataclass, asdict
import base64
import hashlib
import json
from urllib.parse import urlencode
from .kernel.schema import identifier, strict_json
from .kernel.policy import enforce_durable_stop
from .sources.public_http import retrieve


@dataclass(frozen=True)
class Provider:
    provider_id: str
    category: str
    official_api: str
    developer_portal: str
    authentication: str
    capability: str
    adapter_version: str


CROSSREF = Provider('crossref','research','https://api.crossref.org/works',
    'https://www.crossref.org/documentation/retrieve-metadata/rest-api/',
    'PUBLIC_NO_ACCOUNT','bounded_bibliographic_search','1')
CATALOG = {'crossref': CROSSREF}


def request(provider_id, query):
    if provider_id not in CATALOG:raise ValueError('No reviewed adapter for provider')
    if not isinstance(query,str) or not 1<=len(query)<=200 or any(ord(c)<32 for c in query):
        raise ValueError('Bounded query required')
    return CROSSREF.official_api+'?'+urlencode({'query':query,'rows':3,'select':'DOI,title,publisher,type,URL'})


def normalize(response):
    raw=base64.b64decode(response['body_b64'],validate=True)
    if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=response['sha256']:
        raise ValueError('Invalid bounded response digest')
    data=strict_json(raw.decode())
    if data.get('status')!='ok' or data.get('message-type')!='work-list':
        raise ValueError('Unexpected metadata schema')
    items=data['message']['items']
    if not isinstance(items,list) or len(items)>3:raise ValueError('Response count exceeds request')
    output=[];seen=set()
    for item in items:
        doi=item['DOI'];title=item.get('title',[])
        if not isinstance(doi,str) or not doi.startswith('10.') or len(doi)>256 or doi in seen:
            raise ValueError('Invalid or duplicate DOI')
        if not isinstance(title,list) or not title or not all(isinstance(t,str) and len(t)<=2000 for t in title):
            raise ValueError('Invalid title')
        for name in ('publisher','type','URL'):
            if not isinstance(item.get(name),str) or len(item[name])>2048:raise ValueError('Invalid metadata')
        seen.add(doi)
        output.append({k:item[k] for k in ('DOI','title','publisher','type','URL')})
    return output,raw.decode()


def probe(ledger, provider_id, query, trace_id):
    identifier(trace_id)
    if len(trace_id)>40:raise ValueError('Trace too long')
    url=request(provider_id,query)
    contract={'provider':asdict(CATALOG[provider_id]),'url':url,'trace_id':trace_id,'budget_pence':0}
    key='provider-probe-'+trace_id
    with ledger.transaction():
        enforce_durable_stop(ledger)
        rows=ledger.db.execute('SELECT event_key,payload FROM events WHERE event_key IN (?,?)',
                               (key+'-intent',key+'-result')).fetchall()
        existing={k:strict_json(v) for k,v in rows}
        if key+'-intent' in existing:
            if existing[key+'-intent']!=contract:raise ValueError('Trace identity conflict')
            return {'replayed':True,**existing.get(key+'-result',{'state':'BLOCKED_AMBIGUOUS_PRIOR_ATTEMPT'})}
        ledger._append(key+'-intent','decision','opportunity',contract)
    # Stop is checked after reservation and held through this bounded read. Stop
    # latency is graceful (transport timeout); no external writes or retry loop.
    with ledger.transaction():
        enforce_durable_stop(ledger)
        response=retrieve(url)
        result={'trace_id':trace_id,'provider_id':provider_id,'request_url':url,
                'state':'UNAVAILABLE','paid_api_spend_pence':0,'records':[],
                'retrieved_at':response.get('retrieved_at'),'http_status':response.get('http_status'),
                'hops':response.get('hops',[]),'error':response.get('error'),
                'capability':'bounded_bibliographic_search','independent_truth_verified':False,
                'terms_url':CROSSREF.developer_portal}
        if response.get('http_status')==200 and not response.get('error'):
            try:
                items,raw=normalize(response)
                result.update(state='LIVE_VERIFIED',records=items,raw_response=raw,sha256=response['sha256'])
            except (ValueError,KeyError,TypeError,UnicodeError):result['error']='SCHEMA_OR_DIGEST_REJECTED'
        ledger._append(key+'-result','decision','opportunity',result)
        return result


def directory(ledger):
    records=ledger.records('opportunity')
    providers=[]
    for pid,definition in CATALOG.items():
        receipts=[r for r in records if r['key'].startswith('provider-probe-') and
                  r['key'].endswith('-result') and r['payload'].get('provider_id')==pid]
        last=receipts[-1] if receipts else None
        providers.append({**asdict(definition),'implementation_state':'IMPLEMENTED',
            'last_observed_state':last['payload']['state'] if last else 'NOT_TESTED_LIVE',
            'receipt_seq':last['seq'] if last else None,
            'retrieved_at':last['payload']['retrieved_at'] if last else None,
            'health':'HISTORICAL_RECEIPT_NOT_CONTINUOUS_MONITORING',
            'credential_reference':None,'cost_limit_pence':0,
            'pagination':'ONE_PAGE_MAX_3','retries':0})
    # Partial private adapters are visible without claiming consent or live health.
    from .meta_readonly import PROVIDER as meta
    providers.extend([
        {**meta, 'last_observed_state':'AUTH_REQUIRED', 'health':'NOT_VERIFIED',
         'receipt_seq':None, 'credential_reference':None, 'retrieved_at':None},
        {'provider_id':'truelayer-data-v3', 'category':'banking',
         'official_api':'https://api.truelayer.com',
         'implementation_state':'IMPLEMENTED_NOT_AUTHORIZED',
         'capability':'bounded_read_requests_encrypted_receipts_partial',
         'last_observed_state':'AUTH_REQUIRED', 'health':'NOT_VERIFIED',
         'receipt_seq':None, 'credential_reference':None, 'retrieved_at':None,
         'cost_limit_pence':0, 'live_verified':False},
    ])
    return providers
