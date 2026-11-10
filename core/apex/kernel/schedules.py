"""Bounded recurring mission releases; explicit polling, never a hidden daemon.

Missed intervals coalesce to one release. Input evidence timestamps are preserved;
scheduled review does not fetch new sources or refresh expired evidence.
"""
import hashlib
import json
import time
from .engine import canonical, code_digest
from .schema import identifier, strict_json
from .jobs import integer
from .missions import Missions
from .policy import enforce_durable_stop


class Schedules:
    def __init__(self, ledger):
        self.ledger=ledger;self.missions=Missions(ledger)
        with ledger.transaction():
            ledger.db.execute('''CREATE TABLE IF NOT EXISTS mission_schedules (
                id TEXT PRIMARY KEY, packet TEXT NOT NULL, fingerprint TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL, next_due INTEGER NOT NULL,
                remaining INTEGER NOT NULL, issued INTEGER NOT NULL, enabled INTEGER NOT NULL)''')

    def add(self, schedule_id, packet, interval_seconds, first_due, occurrences):
        identifier(schedule_id)
        if len(schedule_id)>16:raise ValueError('Schedule ID too long')
        integer(interval_seconds,60,86400*7);integer(first_due,0,2**53);integer(occurrences,1,20)
        encoded=canonical(packet)
        fingerprint=hashlib.sha256(canonical([packet,interval_seconds,first_due,occurrences,code_digest()]).encode()).hexdigest()
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            prior=self.ledger.db.execute('SELECT fingerprint FROM mission_schedules WHERE id=?',(schedule_id,)).fetchone()
            if prior:
                if prior[0]!=fingerprint:raise ValueError('Schedule identity conflicts')
                return schedule_id
            if self.ledger.db.execute('SELECT count(*) FROM mission_schedules').fetchone()[0]>=100:raise ValueError('Schedule retention cap')
            # Validate using the real mission contract, then roll back the probe.
            self.ledger.db.execute('SAVEPOINT schedule_validation')
            try:self.missions.submit(packet)
            finally:
                self.ledger.db.execute('ROLLBACK TO schedule_validation');self.ledger.db.execute('RELEASE schedule_validation')
            stored={'template':packet,'code_sha256':code_digest()}
            self.ledger.db.execute('INSERT INTO mission_schedules VALUES(?,?,?,?,?,?,0,1)',
                (schedule_id,canonical(stored),fingerprint,interval_seconds,first_due,occurrences))
            self.ledger._append('schedule-'+schedule_id,'decision','opportunity',{
                'schedule_id':schedule_id,'fingerprint':fingerprint,'first_due':first_due,
                'interval_seconds':interval_seconds,'maximum_occurrences':occurrences,'actions_executed':[]})
        return schedule_id

    def poll(self, now=None):
        now=integer(int(time.time()) if now is None else now,0,2**53)
        releases=[]
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            rows=self.ledger.db.execute('SELECT id,packet,interval_seconds,next_due,remaining,issued FROM mission_schedules WHERE enabled=1 AND remaining>0 AND next_due<=? ORDER BY next_due,id LIMIT 4',(now,)).fetchall()
            for sid,encoded,interval,due,remaining,issued in rows:
                saved=strict_json(encoded)
                if saved['code_sha256']!=code_digest():raise ValueError('Schedule code changed; reviewed replacement required')
                packet=saved['template'];trace='sched-'+sid+'-'+str(issued+1)
                packet['trace_id']=trace
                for node in packet['nodes']:node['task']['task_id']=trace+'-'+node['id']
                # Original task/evidence expiry remains binding.
                self.missions.submit(packet)
                next_due=due+((now-due)//interval+1)*interval
                self.ledger.db.execute('UPDATE mission_schedules SET next_due=?,remaining=remaining-1,issued=issued+1 WHERE id=?',(next_due,sid))
                self.ledger._append('schedule-release-'+sid+'-'+str(issued+1),'decision','opportunity',{
                    'schedule_id':sid,'trace_id':trace,'scheduled_for':due,'released_at':now,
                    'coalesced_intervals':(now-due)//interval,'actions_executed':[]})
                releases.append(trace)
        return {'released':releases,'network_calls':0,'scope':'Scheduled review only; evidence not refreshed'}

    def status(self):
        return [dict(zip(['id','interval_seconds','next_due','remaining','issued','enabled'],r)) for r in self.ledger.db.execute('SELECT id,interval_seconds,next_due,remaining,issued,enabled FROM mission_schedules ORDER BY id')]
