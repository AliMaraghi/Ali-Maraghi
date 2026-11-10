"""Validate the committed fail-closed domain configuration; never deploy.

The current release deliberately has no activation path. Endpoint health alone
cannot certify authentication, OAuth integrity or webhook replay protection.
"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'core'))
from apex.kernel.schema import strict_json


def validate(config, ingress):
    expected={s+'.apexcorelab.uk' for s in ('console','api','auth','hooks')}
    if config.get('domain')!='apexcorelab.uk' or config.get('tunnel_name')!='apex-production' or config.get('management')!='remote':
        raise ValueError('Unexpected domain/tunnel scope')
    if set(config.get('routes',{}))!=expected:raise ValueError('Exact requested hostnames required')
    for route in config['routes'].values():
        if route.get('enabled') is not False or route.get('upstream') is not None:
            raise ValueError('Activation blocked until authenticated upstream acceptance')
        if not isinstance(route.get('blocker'),str) or not route['blocker'].strip():
            raise ValueError('Exact blocker required')
    if ingress!={'config':{'ingress':[{'service':'http_status:404'}]}}:
        raise ValueError('Only deny-all remote ingress is currently approved')
    return {'status':'VERIFIED_OFFLINE_DENY_ALL','public_routes_created':0,
            'deployment':'BLOCKED_AUTHORIZATION_AND_UPSTREAM_ACCEPTANCE',
            'zone_active':'UNVERIFIED','universal_ssl_active':'UNVERIFIED',
            'working_urls':[]}


if __name__=='__main__':
    try:
        folder=ROOT/'deploy/cloudflare'
        print(json.dumps(validate(strict_json((folder/'activation.json').read_text()),
                                  strict_json((folder/'remote-deny-all.json').read_text())),indent=2))
    except (ValueError,TypeError,KeyError,OSError):
        print(json.dumps({'status':'INVALID_DOMAIN_CONFIGURATION'}));sys.exit(2)
