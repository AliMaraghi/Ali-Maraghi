"""Produce reviewable API payloads only; never reset existing tunnel ingress."""
import argparse
import json
import re


def plan(account,zone,tunnel,owner):
    for value in (account,zone):
        if not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('Actual account/zone ID required')
    if not re.fullmatch('[0-9a-fA-F-]{36}',tunnel):raise ValueError('Actual tunnel UUID required')
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


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('account','zone','tunnel','owner'):p.add_argument('--'+name,required=True)
    print(json.dumps(plan(**vars(p.parse_args())),indent=2))
