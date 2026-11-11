"""Bounded source-backed product projection; excludes personal/studio payloads.
Historical receipts and offline tests never imply production acceptance.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3]
MANIFESTO='docs/apex_handoff_20261109/APEX_4_4_FINAL_MASTER_MANIFESTO.md'
EXPECTED_HASH='3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd'
DOCS={'requirements':'docs/apex_status/REQUIREMENTS.json','host':'docs/apex_status/HOST_DEPLOYMENT_BOUNDARY.json','checkpoint':'docs/apex_status/CHECKPOINT.json'}


def _read(root,path,limit=2_000_000):
    target=root/path
    try:
        if not target.is_file() or target.is_symlink() or target.stat().st_size>limit:return None
        target.resolve().relative_to(root.resolve())
        return target.read_bytes()
    except (OSError,ValueError):return None


def _document(root,name):
    raw=_read(root,DOCS[name])
    try:
        data=json.loads(raw) if raw else {}
        return data if isinstance(data,dict) else {}
    except (ValueError,TypeError):return {}


def _text(value,limit=180):
    return ''.join(c for c in str(value or '') if ord(c)>=32)[:limit]


def _timestamp(value):
    if not isinstance(value,str):return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except ValueError:return None


def _freshness(value,now):
    stamp=_timestamp(value)
    if not stamp:return 'UNKNOWN_TIMESTAMP'
    age=(now-datetime.fromisoformat(stamp)).total_seconds()
    return 'FUTURE_TIMESTAMP_REJECTED' if age<0 else 'RECENT_HISTORICAL_RECEIPT' if age<=86400 else 'STALE'


def _current_commit(root):
    head=_read(root,'.git/HEAD',256)
    if not head:return None
    value=head.decode(errors='replace').strip()
    if value.startswith('ref: '):
        ref=value[5:]
        if not re.fullmatch(r'refs/heads/[a-zA-Z0-9_/-]+',ref) or '..' in ref:return None
        raw=_read(root,'.git/'+ref,128)
        value=raw.decode(errors='replace').strip() if raw else ''
    return value if re.fullmatch(r'[a-f0-9]{40}',value) else None


def product_snapshot(ledger,root=None):
    root=Path(root) if root is not None else ROOT
    now=datetime.now(timezone.utc);observed=now.isoformat()
    requirements=_document(root,'requirements').get('requirements',[])
    by_id={r.get('requirement_id'):r for r in requirements if isinstance(r,dict)} if isinstance(requirements,list) else {}
    host=_document(root,'host');checkpoint=_document(root,'checkpoint')
    original=_read(root,MANIFESTO);digest=hashlib.sha256(original).hexdigest() if original is not None else None
    tables={r[0] for r in ledger.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    completed={}
    if 'mission_graphs' in tables and 'jobs' in tables:
        for trace,packet in ledger.db.execute('SELECT id,packet FROM mission_graphs ORDER BY id LIMIT 100'):
            # Never project case contents, task prompts or private evidence.
            for node in json.loads(packet).get('nodes',[])[:16]:
                row=ledger.db.execute('SELECT state FROM jobs WHERE id=?',('mg-'+trace+'-'+node['id'],)).fetchone()
                if row and row[0]=='COMPLETE':completed[node['role']]=completed.get(node['role'],0)+1
    # Governing roster: 11 Nov 2026 founder edition (CHANGELOG C4). 8 Nov slots stay
    # preserved as legacy ids; only slot 8-12 has an executable (deterministic) handler.
    roster=['Strategic Intelligence','Scientific Research','Evidence & Verification','Personal Context',
            'Career & Industry','Operations & Executive','Wealth Discovery','Financial Intelligence',
            'Legal & Compliance','Social & Relational','Creative Direction','Screenwriting & Film',
            'Publishing & Audience','Security & Privacy','Health & Longevity','Behavioral Ergonomics',
            'Adversarial Evaluation','Self-Evolution & Systems']
    roles=[]
    for n,name in enumerate(roster,1):
        rid='A-'+str(n);legacy='8-12' if n==3 else None
        roles.append({'id':rid,'name':name,
          'status':'PARTIAL' if legacy else 'NOT_IMPLEMENTED',
          'source':'docs/apex_handoff_20261111/APEX_4_4_MANIFESTO_20261111_FOUNDER_UPLOAD.md',
          'source_line':68+n,'legacy_slot':legacy,
          'source_gap':None,
          'capability':'Deterministic evidence review only (legacy slot 8-12); not independent model reasoning' if legacy else 'No verified executable role handler',
          'permissions':['local_zero_cost_review'] if legacy else [],
          'completed_jobs':completed.get(legacy,0) if legacy else 0,'fully_accepted':False})
    layers=[
      {'id':'I','name':'Open-World Sensing and Knowledge','components':['FTS','TED','Crossref','Evidence journal'],'limitation':'Bounded public reads; no continuous global discovery'},
      {'id':'II','name':'Constitutional Cognition','components':['Mission DAG','Deterministic critic','18 role contracts'],'limitation':'No independent model verification or full role acceptance'},
      {'id':'III','name':'Controlled Execution and Value','components':['Action policy','Fenced jobs','Opportunity review'],'limitation':'No verified external business execution or income'},
      {'id':'IV','name':'Evolution, Reliability and Owner Command','components':['Journal','Evaluation lab','Schedules','Authenticated views'],'limitation':'Production, independent improvement and reboot acceptance unverified'}]
    for layer in layers:layer.update(status='PARTIAL',source='docs/apex_status/ARCHITECTURE_DECISIONS.md')
    research=[];timeline=[];paid=0
    rows=ledger.db.execute("SELECT seq,event_key,kind,payload,digest FROM events WHERE domain='opportunity' ORDER BY seq DESC LIMIT 400").fetchall()
    for seq,key,kind,encoded,event_digest in rows:
        p=json.loads(encoded)
        if key.startswith('field-source-') and p.get('retrieval_status')=='OBSERVED_UNCORROBORATED':
            research.append({'provider':_text(p.get('source')),'trace_id':_text(p.get('trace_id')),
              'status':'OBSERVED_UNCORROBORATED','retrieved_at':_timestamp(p.get('retrieved_at')),
              'source_url':_text(p.get('source_url'),2048),'receipt_seq':seq,
              'sha256':_text(p.get('sha256') or p.get('content_sha256'),64),
              'limitation':'Provider assertion; no independent corroboration'})
        if key.startswith('provider-probe-') and key.endswith('-result'):
            research.append({'provider':_text(p.get('provider_id')),'trace_id':_text(p.get('trace_id')),
              'status':_text(p.get('state')),'retrieved_at':_timestamp(p.get('retrieved_at')),
              'source_url':_text(p.get('request_url'),2048),'receipt_seq':seq,
              'records_count':len(p['records']) if isinstance(p.get('records'),list) else None,
              'sha256':_text(p.get('sha256'),64),'limitation':'Metadata exchange only; scientific truth unverified'})
        if key.startswith('field-result-') or (key.startswith('provider-probe-') and key.endswith('-result')):
            cost=p.get('paid_api_spend_pence')
            if type(cost) is int and cost>=0:paid+=cost
        if key.startswith(('field-result-','mission-','worker-health-','schedule-')) or (key.startswith('provider-probe-') and key.endswith('-result')):
            timeline.append({'id':'event-'+str(seq),'title':_text(p.get('trace_id') or key),'kind':kind,
              'status':_text(p.get('status') or p.get('state')) or 'RECORDED',
              'timestamp':_timestamp(p.get('retrieved_at') or p.get('created_at')),
              'source':'journal:event:'+str(seq),'trace_id':_text(p.get('trace_id')),'digest':event_digest,'ordering':'JOURNAL_SEQUENCE'})
    for receipt in research:receipt['freshness']=_freshness(receipt['retrieved_at'],now)
    research=research[:50]
    providers={r['provider'] for r in research if r['status'] in {'LIVE_VERIFIED','OBSERVED_UNCORROBORATED'}}
    recent={r['provider'] for r in research if r['status'] in {'LIVE_VERIFIED','OBSERVED_UNCORROBORATED'} and r['freshness']=='RECENT_HISTORICAL_RECEIPT'}
    log=_read(root,'.git/logs/HEAD',2_000_000)
    if log:
        for line in log.decode(errors='replace').splitlines()[-80:]:
            before,sep,description=line.partition('\t');parts=before.split()
            if not sep or len(parts)<6 or not re.fullmatch('[a-f0-9]{40}',parts[1]):continue
            try:date=datetime.fromtimestamp(int(parts[-2]),timezone.utc).isoformat()
            except (ValueError,OverflowError,OSError):continue
            # Omit reflog actor names/emails; commit metadata is not a deployment receipt.
            timeline.append({'id':'commit-'+parts[1],'commit':parts[1],'title':_text(description),
              'timestamp':date,'kind':'commit','status':'RECORDED_COMMIT_NOT_DEPLOYMENT','source':'.git/logs/HEAD','ordering':'COMMIT_TIMESTAMP'})
    timeline=sorted(timeline,key=lambda x:x['timestamp'] or '',reverse=True)[:100]
    def metric(mid,label,value,denominator=None,verification='VERIFIED_OFFLINE',source='runtime/kernel.sqlite3',stamp=observed,scope='Deterministic stored-record count'):
        return {'id':mid,'label':label,'value':value,'denominator':denominator,'source':source,
          'timestamp':stamp,'freshness':_freshness(stamp,now),'confidence':scope,'verification':verification}
    metrics=[
      metric('historical_providers','Providers with successful historical exchange',len(providers),3,scope='Known adapters only; not 130-provider coverage'),
      metric('recent_receipts','Providers with receipt within 24 hours',len(recent),3,scope='Historical receipt freshness, not a new health probe'),
      metric('provider_target','Founder provider target',130,None,'UNRESOLVED_INVENTORY','Founder execution directive',None,'Target only; original inventory identities unresolved'),
      metric('accepted_roles','Fully accepted specialist agents',0,18,'NOT_IMPLEMENTED',DOCS['requirements'],None,'No full role acceptance established'),
      metric('deterministic_jobs','Completed deterministic role jobs',completed.get('8-12',0),None,scope='Role 8-12 fixed handler; not independent intelligence'),
      metric('recorded_api_spend','Recorded API expenditure (GBP pence)',paid,None,scope='Latest 400 public result receipts only; excludes hosting/human cost'),
      metric('verified_revenue','Verified received revenue',None,None,'NOT_IMPLEMENTED','No verified income receipt',None,'Unknown, never inferred from contract value')]
    decisions=[
      {'id':'host-access','title':'Host administrator authentication','status':'BLOCKED','reason':'Saved PolicyKit check denied management pending administrator authentication.','next_action':'Connect one approved authenticated host deployment executor; no self-SSH or rule changes.','source':DOCS['host']},
      {'id':'cloudflare-owner','title':'Owner-only Cloudflare Access','status':'BLOCKED','reason':'Rotated management binding and current Access policies not verified.','next_action':'Bind approved credentials; inspect all allow/bypass policies before publication.','source':'docs/apex_status/ACCESS_ORIGIN_REPORT.md'},
      {'id':'inventory','title':'Recover founder provider inventory','status':'BLOCKED','reason':'Authoritative 130 provider identities unresolved.','next_action':'Recover original registry from authorized project sources; never invent identities.','source':'docs/apex_status/PACKAGE_DISCOVERY_20261110.json'},
      {'id':'evidence','title':'Validate candidate opportunities','status':'NOT_IMPLEMENTED','reason':'Notice metadata and deterministic review do not prove fit, demand or income.','next_action':'Review supplier eligibility and independent primary evidence before external action.','source':'docs/apex_status/FIELD_OUTCOME_REPORT.md'}]
    acceptance=[{'id':gate,'label':label,'status':status,'source':source} for gate,label,status,source in [
      ('A','Public DNS','BLOCKED','docs/apex_status/INFRASTRUCTURE_RECHECK.json'),
      ('B','Valid public HTTPS','BLOCKED','docs/apex_status/ACCESS_ORIGIN_REPORT.md'),
      ('C','Unauthorized public access denied','BLOCKED','docs/apex_status/ACCESS_ORIGIN_REPORT.md'),
      ('D','Founder public login','BLOCKED','docs/apex_status/ACCESS_ORIGIN_REPORT.md'),
      ('E','Actual iPhone Safari acceptance','NOT_IMPLEMENTED','No device receipt'),
      ('G','Laptop-independent scheduled execution','BLOCKED',DOCS['host']),
      ('I','Host restart/reboot recovery','BLOCKED',DOCS['host']),
      ('J','Offsite backup restoration','NOT_IMPLEMENTED','No offsite restore receipt')]]
    return {'generated_at':observed,'commit':_current_commit(root),'manifesto':{
      'status':'VERIFIED' if digest==EXPECTED_HASH else 'FAILED' if digest else 'MISSING','sha256':digest,'expected_sha256':EXPECTED_HASH,'source':MANIFESTO},
      'roles':roles,'layers':layers,'metrics':metrics,'timeline':timeline,'decisions':decisions,'acceptance':acceptance,'research':research,
      'provider_inventory':{'target':130,'recovered':None,'status':'UNRESOLVED','known_adapter_count':3},
      'host_observation':{'observed_at':_timestamp(host.get('observed_at')),'freshness':_freshness(host.get('observed_at'),now),'cloudflared_state':host.get('cloudflared',{}).get('active','UNKNOWN'),'scope':'Saved observation, not current tunnel health','source':DOCS['host']},
      'tests':{'source':DOCS['checkpoint'],'recorded':checkpoint.get('tests',{}),'scope':'Historical summary; not production acceptance'},
      'journey':{'started':'Source preservation and offline evidence kernel','built':'Fenced jobs, public adapters, encrypted Gmail sync engine and authenticated views','works':'Stored public receipts, local replay and deterministic review','blocked':'Host authentication, owner-only Access and live publication','next':'Deploy validated release through authorized host and Cloudflare management','value':'Inspectable evidence and reproducible local controls; revenue/time savings unverified'},
      'projection_limits':{'journal_events':400,'timeline_items':100,'research_receipts':50,'private_domains_excluded':['personal','studio'],'full_acceptance':'OPEN'}}
