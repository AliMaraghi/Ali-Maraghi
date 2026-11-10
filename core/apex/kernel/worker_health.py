"""Audited worker observations. A fresh heartbeat is not deployment proof."""
import time


def record(ledger, state, interval, error_type=None):
    if state not in {'CYCLE_COMPLETED','CYCLE_FAILED','STOPPED','EXITED','RETRY_EXHAUSTED'}:
        raise ValueError('Invalid worker observation')
    if type(interval) is not int or not 60 <= interval <= 3600:
        raise ValueError('Invalid heartbeat interval')
    if error_type is not None and (not isinstance(error_type,str) or not error_type.isidentifier() or len(error_type)>100):
        raise ValueError('Only redacted error class permitted')
    with ledger.transaction():
        ledger.db.execute('''CREATE TABLE IF NOT EXISTS worker_health (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation INTEGER NOT NULL,
            observed_at INTEGER NOT NULL, state TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
            error_type TEXT)''')
        row=ledger.db.execute('SELECT generation FROM worker_health WHERE singleton=1').fetchone()
        generation=(row[0] if row else 0)+1
        now=int(time.time())
        ledger.db.execute('INSERT OR REPLACE INTO worker_health VALUES(1,?,?,?,?,?)',
                          (generation,now,state,interval,error_type))
        ledger._append('worker-health-'+str(generation),'decision','opportunity',
                       {'state':state,'observed_at':now,'interval_seconds':interval,'error_type':error_type,
                        'scope':'LOCAL_PROCESS_OBSERVATION_NOT_DEPLOYMENT_PROOF'})


def status(ledger, now=None):
    now=int(time.time()) if now is None else now
    if not ledger.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='worker_health'").fetchone():
        return {'state':'NOT_OBSERVED'}
    row=ledger.db.execute('SELECT observed_at,state,interval_seconds,error_type FROM worker_health WHERE singleton=1').fetchone()
    if row is None:return {'state':'NOT_OBSERVED'}
    observed,state,interval,error=row
    age=now-observed
    return {'state':state,'observed_at':observed,'age_seconds':age,
            'fresh':0<=age<=interval*2,'error_type':error,
            'scope':'LOCAL_PROCESS_OBSERVATION_NOT_DEPLOYMENT_PROOF'}
