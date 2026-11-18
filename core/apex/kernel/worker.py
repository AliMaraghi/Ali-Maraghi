"""Supervisable local scheduler loop with fixed handlers.

Networking happens only for an owner-armed connector schedule AND an explicit
administrator config path passed at start; otherwise connector runs fail closed.
"""
import json
import signal
from .memory import Ledger
from .schedules import Schedules
from .policy import enforce_durable_stop


def run_connectors(ledger, scheduler, google_config):
    outcomes=[]
    for connector,owner_digest,issued in scheduler.pending_connectors():
        state,error=None,None
        try:
            if connector!='gmail':raise PermissionError('No handler')
            if google_config is None:raise PermissionError('Worker not configured for Google')
            from ..google_web import scheduled_gmail_sync
            state=scheduled_gmail_sync(ledger,google_config,owner_digest)['status']
        except Exception as failure:  # Settled and audited; never retried within this cycle.
            state,error='CONNECTOR_FAILED',type(failure).__name__
        settled=scheduler.record_connector(connector,issued,state,error)
        outcomes.append({'connector':connector,'state':state,'error_type':error,
                         'disabled':bool(settled and settled['disabled'])})
    return outcomes


def cycle(root, google_config=None):
    with Ledger(root) as ledger:
        scheduler=Schedules(ledger)
        with ledger.transaction():
            try:enforce_durable_stop(ledger)
            except PermissionError:return {'state':'STOPPED','executed':[]}
        outcomes=[]
        try:
            polled=scheduler.poll();released=polled['released']
            outcomes.extend({'schedule_id':sid,'state':'BLOCKED_CODE_CHANGED_REVIEW_REQUIRED'} for sid in polled['blocked_code_changed'])
        except ValueError:released=[];outcomes.append({'stage':'schedule','state':'BLOCKED_INPUT_OR_CODE'})
        try:connector_outcomes=run_connectors(ledger,scheduler,google_config)
        except PermissionError:connector_outcomes=[]  # Durable stop raised during settlement.
        if google_config is not None:
            # Encrypted off-site journal copy, at most once a day; it stays idle until the owner
            # has granted the Drive scope and placed the passphrase file. Never fatal to the cycle.
            try:
                from ..google_web import scheduled_offsite_backup
                backup_state=scheduled_offsite_backup(ledger,google_config,root)
                if backup_state:outcomes.append({'stage':'offsite_backup','state':backup_state})
            except Exception as failure:
                outcomes.append({'stage':'offsite_backup','state':'FAILED','error_type':type(failure).__name__})
        # Persist admission before executing. A crash may defer an admitted graph
        # by one rotation, but cannot repeatedly pin the head of the queue.
        # Job leases, not this cursor, fence actual execution attempts.
        with ledger.transaction():
            enforce_durable_stop(ledger)
            ledger.db.execute("""CREATE TABLE IF NOT EXISTS worker_dispatch (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                last_trace TEXT NOT NULL, generation INTEGER NOT NULL)""")
            ledger.db.execute("INSERT OR IGNORE INTO worker_dispatch VALUES(1,'',0)")
            last,generation=ledger.db.execute(
                'SELECT last_trace,generation FROM worker_dispatch WHERE singleton=1').fetchone()
            traces=[r[0] for r in ledger.db.execute(
                'SELECT id FROM mission_graphs ORDER BY id')]
            ordered=[t for t in traces if t>last]+[t for t in traces if t<=last]
            admitted=[]
            for trace in ordered:
                state=scheduler.missions.status(trace)
                if all(n['state'] in {'COMPLETE','DEAD'} for n in state['nodes']):
                    continue
                admitted.append(trace)
                if len(admitted)==4:break
            if admitted:
                ledger.db.execute('UPDATE worker_dispatch SET last_trace=?,generation=? WHERE singleton=1',
                                  (admitted[-1],generation+1))
                ledger._append('dispatch-'+str(generation+1),'decision','opportunity',
                               {'admitted':admitted,'previous_cursor':last,
                                'status':'ADMITTED_NOT_EXECUTED'})
        for trace in admitted:
            try:
                result=scheduler.missions.tick(trace,root,'managed-local-worker')
                outcomes.append({'trace_id':trace,'state':'TICK_COMPLETED','nodes':result['nodes']})
            except (ValueError,PermissionError):
                outcomes.append({'trace_id':trace,'state':'BLOCKED_INPUT_CODE_OR_STOP'})
        return {'state':'CYCLE_COMPLETED','released':released,'outcomes':outcomes,
                'connector_outcomes':connector_outcomes,
                'connector_runs':len(connector_outcomes),'paid_api_spend_pence':0}


def serve(root, interval=60, google_config=None):
    if type(interval) is not int or not 60<=interval<=3600:raise ValueError('Worker interval out of bounds')
    import threading
    stopped=threading.Event()
    def stop(*_):stopped.set()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    from .worker_health import record
    failures = 0
    while not stopped.is_set():
        try:result=cycle(root,google_config)
        except Exception as error:result={'state':'CYCLE_FAILED','error_type':type(error).__name__}
        failures = failures+1 if result['state']=='CYCLE_FAILED' else 0
        if failures >= 3:
            result['state']='RETRY_EXHAUSTED'
        # If audit storage itself fails, exit immediately for supervisor diagnosis.
        with Ledger(root) as ledger:
            record(ledger,result['state'],interval,result.get('error_type'))
        print(json.dumps(result),flush=True)
        if failures >= 3:
            raise SystemExit(78)  # Supervisor must not automatically restart exhausted work.
        stopped.wait(interval)
    with Ledger(root) as ledger:
        record(ledger,'EXITED',interval)
