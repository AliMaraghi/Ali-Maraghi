"""Supervisable local scheduler loop, fixed handlers and no implicit networking."""
import json
import signal
from .memory import Ledger
from .schedules import Schedules
from .policy import enforce_durable_stop


def cycle(root):
    with Ledger(root) as ledger:
        scheduler=Schedules(ledger)
        with ledger.transaction():
            try:enforce_durable_stop(ledger)
            except PermissionError:return {'state':'STOPPED','executed':[]}
        outcomes=[]
        try:released=scheduler.poll()['released']
        except ValueError:released=[];outcomes.append({'stage':'schedule','state':'BLOCKED_INPUT_OR_CODE'})
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
                'network_calls':0,'paid_api_spend_pence':0}


def serve(root, interval=60):
    if type(interval) is not int or not 60<=interval<=3600:raise ValueError('Worker interval out of bounds')
    import threading
    stopped=threading.Event()
    def stop(*_):stopped.set()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    from .worker_health import record
    failures = 0
    while not stopped.is_set():
        try:result=cycle(root)
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
