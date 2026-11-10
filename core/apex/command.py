"""Unified local entrypoint; reuses the existing kernel and development journal."""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from .kernel.memory import Ledger
from .kernel.jobs import Jobs
from .kernel.policy import KillState
from .kernel.schema import strict_json
from .kernel.evidence import read_local

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    p=argparse.ArgumentParser(description='APEX explicit development operations; no production lifecycle')
    s=p.add_subparsers(dest='command',required=True)
    s.add_parser('doctor')
    s.add_parser('test-all')
    connectors=s.add_parser('connectors');connectors.add_argument('operation',choices=['verify'])
    s.add_parser('audit')
    s.add_parser('costs')
    wo=s.add_parser('worker');wo.add_argument('--once',action='store_true');wo.add_argument('--interval',type=int,default=60)
    mi=s.add_parser('missions');mi.add_argument('operation',choices=['submit','tick','status']);mi.add_argument('target');mi.add_argument('--worker',default='local-mission-worker')
    sc=s.add_parser('schedules');sc.add_argument('operation',choices=['add','poll','status']);sc.add_argument('--input')
    st=s.add_parser('status');st.add_argument('--json',action='store_true')
    pi=s.add_parser('pilot');pi.add_argument('mission');pi.add_argument('--source',choices=['live'],required=True);pi.add_argument('--read-only',action='store_true',required=True)
    re=s.add_parser('report');re.add_argument('--trace',required=True)
    stop=s.add_parser('stop');stop.add_argument('--level',choices=[k.value for k in KillState if k is not KillState.RUNNING],required=True)
    view=s.add_parser('owner-view');view.add_argument('--trace',required=True);view.add_argument('--port',type=int,default=8765)
    dec=s.add_parser('decide');dec.add_argument('--trace',required=True);dec.add_argument('--decision',choices=['approve-internal','reject-internal'],required=True)
    for name in ['up','down']:
        q=s.add_parser(name);q.add_argument('--dry-run',action='store_true')
    k=s.add_parser('kernel');k.add_argument('args',nargs=argparse.REMAINDER)
    args=p.parse_args(argv)
    try:
        if args.command=='kernel':
            from .kernel.cli import main as kernel
            return kernel(args.args)
        if args.command=='test-all':
            return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/test_offline.py')],cwd=ROOT).returncode
        if args.command=='worker':
            from .kernel.worker import cycle,serve
            if args.once:result=cycle(ROOT)
            else:serve(ROOT,args.interval);return 0
        elif args.command=='schedules':
            from .kernel.schedules import Schedules
            with Ledger(ROOT) as ledger:
                schedules=Schedules(ledger)
                if args.operation=='add':
                    packet=strict_json(read_local(ROOT,args.input,524288).decode())
                    result={'schedule_id':schedules.add(**packet)}
                elif args.operation=='poll':result=schedules.poll()
                else:result={'schedules':schedules.status()}
        elif args.command=='missions':
            from .kernel.missions import Missions
            if args.operation=='status':
                with Ledger.read_only(ROOT) as ledger:result=Missions.read_only(ledger).status(args.target)
            else:
                with Ledger(ROOT) as ledger:
                    scheduler=Missions(ledger)
                    result=({'trace_id':scheduler.submit(strict_json(read_local(ROOT,args.target,524288).decode()))}
                            if args.operation=='submit' else scheduler.tick(args.target,ROOT,args.worker))
        elif args.command in {'connectors','audit','costs'}:
            with Ledger.read_only(ROOT) as ledger:
                if args.command=='connectors':
                    from .connectors import verify
                    result=verify(ledger)
                elif args.command=='audit':
                    result={'verified_events':ledger.verify(),'status':'VERIFIED_OFFLINE',
                            'scope':'Local hash chain; not protected against privileged owner rewrite'}
                else:
                    events=ledger.records('opportunity')
                    runs=[e['payload'] for e in events if e['key'].startswith('field-result-')]
                    result={'recorded_field_runs':len(runs),'paid_api_spend_pence':sum(r['paid_api_spend_pence'] for r in runs),
                            'currency':'GBP','budget_pence':0,'scope':'Recorded field runs only; hosting/human costs NOT_MEASURED'}
        elif args.command=='doctor':
            result={'workspace':str(ROOT),'mode':'DEVELOPMENT_ONLY','database':'runtime/kernel.sqlite3',
                'dependencies':{name:importlib.util.find_spec(name) is not None for name in ['fastapi','httpx','psycopg','uvicorn']},
                'service_state':'NOT_INSPECTED_NO_DOCKER_OR_PRODUCTION_ACCESS',
                'compose':'Existing compose.yaml is not approved staging isolation; not started',
                'n8n':'NOT_PRESENT_IN_COMPOSE','remote_owner_access':'BLOCKED_PRIVATE_TLS_AND_OWNER_ACCEPTANCE',
                'companies_house':'BLOCKED_API_CREDENTIALS_NOT_PROVIDED','paid_api_budget_pence':0}
        elif args.command in {'up','down'}:
            result={'status':'BLOCKED_STAGING_LIFECYCLE','mode':args.command,'dry_run':args.dry_run,
                'reason':'No reviewed isolated staging stack, pinned images, dependency lock, migrations or deployment approval; no service command executed'}
            print(json.dumps(result,indent=2));return 2
        elif args.command=='status':
            with Ledger.read_only(ROOT) as ledger:
                result=Jobs.read_only(ledger).status()
                result['ledger_events']=ledger.verify()
                if ledger.db.execute("SELECT 1 FROM sqlite_master WHERE name='field_runs'").fetchone():
                    result['field_runs']=[dict(zip(['trace_id','state','result_seq'],r)) for r in ledger.db.execute('SELECT trace_id,state,result_seq FROM field_runs ORDER BY trace_id')]
        elif args.command=='report':
            from .kernel.field import report
            with Ledger.read_only(ROOT) as ledger: result=report(ledger,args.trace)
        elif args.command=='pilot':
            from .kernel.field import Mission,run
            mission=Mission.parse(strict_json(read_local(ROOT,args.mission,16384).decode()))
            with Ledger(ROOT) as ledger: result=run(mission,ROOT,ledger,network_authorized=True)
        elif args.command=='stop':
            with Ledger(ROOT) as ledger:
                queue=Jobs(ledger);queue.set_stop(KillState(args.level))
                result={'state':queue.control().value,'scope':'Durable development queue/field gateway; graceful, no external credential revocation'}
        elif args.command=='decide':
            from .kernel.field import owner_decision
            with Ledger(ROOT) as ledger: seq=owner_decision(ledger,ROOT,args.trace,args.decision=='approve-internal')
            result={'ledger_seq':seq,'external_actions_executed':[]}
        else:
            from .kernel.owner_view import serve
            serve(ROOT,args.trace,args.port);return 0
        print(json.dumps(result,indent=2,ensure_ascii=True,allow_nan=False))
        return 2 if result.get('status')=='BLOCKED_EXTERNAL_FETCH' else 0
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as error:
        print(json.dumps({'status':'BLOCKED','error_type':type(error).__name__}))
        return 2


if __name__=='__main__': sys.exit(main())
