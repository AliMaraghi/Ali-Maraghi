"""Supervisable local scheduler loop, fixed handlers and no implicit networking."""
import json
import signal
import time
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
        # Each cycle has a strict admission cap; historical complete graphs skipped.
        for (trace,) in ledger.db.execute('SELECT id FROM mission_graphs ORDER BY id').fetchall():
            state=scheduler.missions.status(trace)
            if all(n['state'] in {'COMPLETE','DEAD'} for n in state['nodes']):continue
            if len(outcomes)>=4:break
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
    while not stopped.is_set():
        try:result=cycle(root)
        except Exception as error:result={'state':'CYCLE_FAILED','error_type':type(error).__name__}
        print(json.dumps(result),flush=True)
        stopped.wait(interval)
