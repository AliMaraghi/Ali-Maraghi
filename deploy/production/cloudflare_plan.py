"""Produce reviewable API payloads only; never reset existing tunnel ingress."""
import argparse
import json
import re
import uuid
from pathlib import Path


def plan(account,zone,tunnel,owner):
    for value in (account,zone):
        if not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('Actual account/zone ID required')
    try:
        if str(uuid.UUID(tunnel))!=tunnel.lower():raise ValueError('Actual tunnel UUID required')
    except (ValueError,AttributeError):raise ValueError('Actual tunnel UUID required')
    if not re.fullmatch(r'[^\s@,<>]+@[^\s@,<>]+\.[^\s@,<>]+',owner):raise ValueError('Exact owner identity required')
    return {'state':'PREPARED_NOT_APPLIED','account_id':account,'zone_id':zone,'tunnel_id':tunnel,
      'access_application':{'name':'APEX Founder Console','domain':'console.apexcorelab.uk','type':'self_hosted','session_duration':'1h'},
      'access_policy':{'name':'Founder only','decision':'allow','include':[{'email':{'email':owner}}]},
      'dns_record':{'type':'CNAME','name':'console.apexcorelab.uk','content':tunnel+'.cfargotunnel.com','proxied':True,'ttl':1},
      'ingress_entry_to_merge':{'hostname':'console.apexcorelab.uk','service':'http://127.0.0.1:8765'},
      'preconditions':['Verify zone active, tunnel identity and remote health','Snapshot current DNS/Access/ingress configuration',
        'Reject conflicting DNS; upsert only matching identity','Create owner-only Access app/policy first; inspect all existing allow/bypass policies',
        'Bind actual AUD/team issuer/owner/current JWKS at origin','Prove signed-owner200 and anonymous401 at origin',
        'Merge ingress preserving other routes and terminal catchall; never replace whole config blindly',
        'Publish DNS only after gates pass; verify external denial and owner HTTPS access'],
      'unpublished':['api.apexcorelab.uk','auth.apexcorelab.uk','hooks.apexcorelab.uk'],
      'minimum_token_scopes':['Account Cloudflare Tunnel Edit','Account Access Apps and Policies Edit','Zone DNS Edit','Zone Read','Zone SSL and Certificates Read'],
      'credential_rule':'Rotated approved management token only; never CLI argument or log; runtime tunnel credential separate'}


def validate_access_policies(policies, owner):
    """Review ALL policies of the exact app; never infer remote completeness.

    Call only after all API pages have been collected. This rejects any alternate
    allow identity, broad group or bypass. Additional require/exclude predicates
    can restrict access further, but successful owner login remains a live gate.
    """
    if not isinstance(policies,list) or not policies:raise ValueError('Complete nonempty policy list required')
    allow=False
    for policy in policies:
        if not isinstance(policy,dict):raise ValueError('Invalid policy')
        decision=policy.get('decision')
        if decision=='deny':continue
        if decision!='allow':raise ValueError('Bypass or non-owner policy forbidden')
        if policy.get('include')!=[{'email':{'email':owner}}]:
            raise ValueError('Allow policy must name only the exact owner')
        allow=True
    if not allow:raise ValueError('No owner allow policy found')
    return {'status':'OWNER_ONLY_POLICY_SNAPSHOT_VALIDATED','live_policy_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('account','zone','tunnel','owner'):p.add_argument('--'+name,required=True)
    p.add_argument('--existing-policies',type=Path)
    args=vars(p.parse_args());path=args.pop('existing_policies')
    result=plan(**args)
    if path is not None:
        if path.stat().st_size>1048576:raise ValueError('Policy snapshot too large')
        result['policy_snapshot']=validate_access_policies(json.loads(path.read_text()),args['owner'])
    print(json.dumps(result,indent=2))
