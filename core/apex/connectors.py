"""Conservative connector inventory from installed adapters and durable receipts.

No secret scanning or implicit OAuth grants. A registered account, environment
variable or old successful response is not a currently verified connection.
"""
from datetime import datetime, timezone, timedelta
from .kernel.schema import timestamp


def verify(ledger):
    providers=[]
    records=ledger.records('opportunity')
    for pid, endpoint, auth in [
        ('fts','https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages','public'),
        ('ted','https://api.ted.europa.eu/v3/notices/search','public')]:
        observations=[r['payload'] for r in records if r['key'].startswith('field-source-')
                      and r['payload'].get('source')==pid and 'retrieval_status' in r['payload']]
        last=observations[-1] if observations else {}
        captured=last.get('retrieved_at')
        fresh=bool(captured and datetime.now(timezone.utc)-timedelta(hours=24) <= timestamp(captured) <= datetime.now(timezone.utc))
        valid=last.get('retrieval_status')=='OBSERVED_UNCORROBORATED'
        providers.append({'provider_id':pid,'category':'public_procurement','official_api':endpoint,
            'authentication_method':auth,'required_scopes':['public_read'],
            'capabilities':['bounded_notice_search'],'account_status':'NOT_REQUIRED',
            'credential_status':'NOT_REQUIRED','permission_status':'EXPLICIT_LOCAL_COMMAND_REQUIRED',
            'connection_status':'VERIFIED_LIVE' if fresh and valid else 'IMPLEMENTED_UNVERIFIED',
            'rate_limit':'One page/request; max4 requests/mission; zero retries',
            'cost_limit':{'currency':'GBP','pence':0},'last_verified':captured if valid else None,
            'health_check':'Historical receipt inspection only; no new network request',
            'error_details':last.get('error'),'receipt_fresh':fresh})
    from .providers import directory
    return {'additional_adapters':directory(ledger),'providers':providers,'registered_adapter_count':len(providers),
            'requested_master_register':'PROVIDERS_MASTER_REGISTER.csv',
            'master_register_status':'MISSING_NOT_FABRICATED',
            'credential_discovery':'BLOCKED_AUTHORIZATION: no approved secret-store binding supplied; private stores not scanned',
            'other_requested_services':'NOT_IMPLEMENTED or BLOCKED_AUTHORIZATION; no connections inferred'}
