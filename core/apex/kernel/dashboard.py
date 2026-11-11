"""Read-only projections of the existing journal; no fabricated operational KPIs."""
import json
from html import escape
from .jobs import Jobs
from .missions import Missions
from ..connectors import verify


def snapshot(ledger,root=None):
    from .worker_health import status as worker_status
    count=ledger.verify()
    queue=Jobs.read_only(ledger).status()
    tables={r[0] for r in ledger.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missions=[]
    if 'mission_graphs' in tables:
        missions=[Missions.read_only(ledger).status(r[0]) for r in ledger.db.execute('SELECT id FROM mission_graphs ORDER BY id')]
    schedules=[]
    if 'mission_schedules' in tables:
        schedules=[dict(zip(['id','next_due','remaining','issued','enabled'],r)) for r in ledger.db.execute('SELECT id,next_due,remaining,issued,enabled FROM mission_schedules ORDER BY id')]
    reports=[]
    for event in ledger.records('opportunity'):
        if not event['key'].startswith('field-result-'):continue
        p=event['payload']
        reports.append({'trace_id':p['trace_id'],'ledger_seq':event['seq'],'status':p['status'],
            'unverified_candidates':p['candidate_count'],'excluded':p['excluded_count'],
            'paid_api_spend_pence':p['paid_api_spend_pence'],
            'sources':[{'url':o['source_url'],'retrieved_at':o.get('retrieved_at'),
                        'status':o['retrieval_status']} for o in p['observations']],
            'next_internal_action':p['next_internal_action'],
            'independent_outcome':'NOT_MEASURED'})
    from .product_evidence import product_snapshot
    return {'product':product_snapshot(ledger,root),'mode':'LOCAL_AUTHENTICATED_DEVELOPMENT_VIEW','audit_events_verified':count,
        'worker':worker_status(ledger),'queue':queue,'missions':missions,'schedules':schedules,'providers':verify(ledger),
        'reports':reports,'recorded_field_api_spend_pence':sum(r['paid_api_spend_pence'] for r in reports),
        'financial_outcome':'NO_VERIFIED_INCOME_RECORDED','independent_improvement':'NOT_MEASURED',
        'runtime_service':'NOT_VERIFIED_DEPLOYED','remote_https':'NOT_VERIFIED',
        'full_acceptance':'OPEN','private_provider_authorization':'NOT_BOUND'}


def render(data, reports_only=False):
    from .console_ui import render as render_console
    return render_console(data,reports_only)
