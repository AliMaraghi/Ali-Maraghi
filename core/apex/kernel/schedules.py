"""Bounded recurring mission releases; explicit polling, never a hidden daemon.

Missed intervals coalesce to one release. Input evidence timestamps are preserved;
scheduled review does not fetch new sources or refresh expired evidence.
"""
import hashlib
import json
import time
import uuid
from .engine import canonical, code_digest
from .schema import identifier, strict_json
from .jobs import integer
from .missions import Missions
from .policy import enforce_durable_stop


# Fixed allowlist. Each connector has exactly one reviewed handler in worker.py;
# a schedule row never names code, endpoints, credentials or arbitrary parameters.
CONNECTORS=frozenset({'gmail'})
CONNECTOR_FAILURE_LIMIT=3


class Schedules:
    def __init__(self, ledger):
        self.ledger=ledger;self.missions=Missions(ledger)
        with ledger.transaction():
            ledger.db.execute('''CREATE TABLE IF NOT EXISTS connector_schedules (
                connector TEXT PRIMARY KEY, owner_digest TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL, next_due INTEGER NOT NULL,
                remaining INTEGER NOT NULL, issued INTEGER NOT NULL,
                failures INTEGER NOT NULL, pending INTEGER NOT NULL, enabled INTEGER NOT NULL)''')
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

    def arm_connector(self, connector, owner_digest, interval_seconds, first_due, occurrences):
        """Caller must be the authenticated owner route; this is not authorization."""
        if connector not in CONNECTORS:raise ValueError('Unknown connector')
        if not isinstance(owner_digest,str) or len(owner_digest)!=64 or not all(c in '0123456789abcdef' for c in owner_digest):
            raise ValueError('Owner digest required')
        integer(interval_seconds,300,86400);integer(first_due,0,2**53);integer(occurrences,1,2016)
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            # Re-arming resets the bounded budget and failure count; the cursor lives with the sync.
            self.ledger.db.execute('INSERT OR REPLACE INTO connector_schedules VALUES(?,?,?,?,?,0,0,0,1)',
                (connector,owner_digest,interval_seconds,first_due,occurrences))
            self.ledger._append('connector-arm-'+connector+'-'+str(first_due),'decision','personal',{
                'connector':connector,'interval_seconds':interval_seconds,'first_due':first_due,
                'maximum_occurrences':occurrences,'phase':'OWNER_ARMED','actions_executed':[]})
        return self.connector_status()

    def disarm_connector(self, connector, reason='OWNER_DISARMED'):
        if connector not in CONNECTORS:raise ValueError('Unknown connector')
        with self.ledger.transaction():
            changed=self.ledger.db.execute('UPDATE connector_schedules SET enabled=0,pending=0 WHERE connector=? AND enabled=1',(connector,)).rowcount
            if changed:
                self.ledger._append('connector-disarm-'+connector+'-'+str(int(time.time()))+'-'+reason,'decision','personal',
                                    {'connector':connector,'phase':reason})
        return self.connector_status()

    def pending_connectors(self):
        return self.ledger.db.execute('SELECT connector,owner_digest,issued FROM connector_schedules WHERE enabled=1 AND pending=1 ORDER BY connector').fetchall()

    def record_connector(self, connector, issued, state, error_type=None):
        """Settle one released run. Repeated failure or resync disables, never loops."""
        if connector not in CONNECTORS or not isinstance(state,str) or len(state)>64:raise ValueError('Invalid connector outcome')
        if error_type is not None and (not isinstance(error_type,str) or len(error_type)>64):raise ValueError('Invalid error type')
        ok=state=='PAGE_SYNCHRONIZED'
        with self.ledger.transaction():
            row=self.ledger.db.execute('SELECT failures,pending,issued FROM connector_schedules WHERE connector=?',(connector,)).fetchone()
            if row is None or row[1]!=1 or row[2]!=issued:return None  # Disarmed or re-armed meanwhile.
            failures=0 if ok else row[0]+1
            disable=not ok and (failures>=CONNECTOR_FAILURE_LIMIT or state=='RESYNC_REQUIRED')
            self.ledger.db.execute('UPDATE connector_schedules SET pending=0,failures=?,enabled=? WHERE connector=?',
                                   (failures,0 if disable else 1,connector))
            self.ledger._append('connector-run-'+connector+'-'+str(issued)+'-'+uuid.uuid4().hex[:8],'decision','personal',{
                'connector':connector,'release':issued,'state':state,'error_type':error_type,
                'consecutive_failures':failures,'disabled':disable})
        return {'connector':connector,'state':state,'disabled':disable}

    def connector_status(self):
        return [dict(zip(['connector','interval_seconds','next_due','remaining','issued','failures','pending','enabled'],r))
                for r in self.ledger.db.execute('SELECT connector,interval_seconds,next_due,remaining,issued,failures,pending,enabled FROM connector_schedules ORDER BY connector')]

    def poll(self, now=None):
        now=integer(int(time.time()) if now is None else now,0,2**53)
        releases=[];blocked=[]
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            rows=self.ledger.db.execute('SELECT id,packet,interval_seconds,next_due,remaining,issued FROM mission_schedules WHERE enabled=1 AND remaining>0 AND next_due<=? ORDER BY next_due,id LIMIT 104',(now,)).fetchall()
            for sid,encoded,interval,due,remaining,issued in rows:
                saved=strict_json(encoded)
                if saved['code_sha256']!=code_digest():
                    # Stays blocked and unmodified; it must not starve other schedules.
                    blocked.append(sid);continue
                if len(releases)>=4:break
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
            connectors=[]
            # An unsettled (pending) release blocks further releases: no overlap, no backlog.
            for name,interval,due in self.ledger.db.execute('SELECT connector,interval_seconds,next_due FROM connector_schedules WHERE enabled=1 AND pending=0 AND remaining>0 AND next_due<=? ORDER BY connector',(now,)).fetchall():
                next_due=due+((now-due)//interval+1)*interval
                self.ledger.db.execute('UPDATE connector_schedules SET pending=1,next_due=?,remaining=remaining-1,issued=issued+1 WHERE connector=?',(next_due,name))
                connectors.append(name)
        return {'released':releases,'blocked_code_changed':blocked,'connectors_released':connectors,'network_calls':0,
                'scope':'Scheduled review only; evidence not refreshed; connector runs execute in worker'}

    def status(self):
        return [dict(zip(['id','interval_seconds','next_due','remaining','issued','enabled'],r)) for r in self.ledger.db.execute('SELECT id,interval_seconds,next_due,remaining,issued,enabled FROM mission_schedules ORDER BY id')]
