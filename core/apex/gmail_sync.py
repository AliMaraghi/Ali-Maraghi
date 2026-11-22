"""Encrypted Gmail sync contract. Requires a separately authorized read-only client.

client.get(resource, params) must implement official users/me GET endpoints and
raise GmailError(status). No ChatGPT tokens, writes, automatic consent or sends.
"""
import hashlib
import json
from cryptography.fernet import Fernet


METADATA_HEADERS=('From','To','Subject','Date','Message-ID','In-Reply-To')


def minimized_headers(payload):
    """Do not trust a provider response to honor requested metadata fields."""
    if not isinstance(payload,dict):raise ValueError('Invalid metadata payload')
    headers=payload.get('headers',[])
    if not isinstance(headers,list) or len(headers)>100:raise ValueError('Invalid header collection')
    allowed={name.lower():name for name in METADATA_HEADERS}
    result=[]
    for header in headers:
        if not isinstance(header,dict) or not isinstance(header.get('name'),str):
            raise ValueError('Invalid header shape')
        name=allowed.get(header['name'].lower())
        if name is None:continue
        value=header.get('value')
        if not isinstance(value,str) or len(value)>8192 or '\x00' in value:
            raise ValueError('Invalid bounded header value')
        result.append({'name':name,'value':value})
    return result


# Owner decision 22 Nov 2026: raise the pilot limit from 100 to a fixed 2,000 threads, still metadata only.
THREAD_CAP=2000
STATE_BYTES_CAP=8_000_000

class GmailError(Exception):
    def __init__(self,status):self.status=status;super().__init__('Gmail request failed')


class GmailSync:
    def __init__(self,ledger,key,owner,policy=None):
        self.ledger=ledger;self.cipher=Fernet(key);self.owner=owner;self.policy=policy
        if not isinstance(owner,str) or '@' not in owner:raise ValueError('Owner identity required')
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS google_private_sync (account TEXT PRIMARY KEY, encrypted BLOB NOT NULL, generation INTEGER NOT NULL)')
        # Unkeyed pseudonym, not anonymization: known email addresses remain guessable.
        self.account=hashlib.sha256(owner.encode()).hexdigest()

    def load(self):
        row=self.ledger.db.execute('SELECT encrypted,generation FROM google_private_sync WHERE account=?',(self.account,)).fetchone()
        if row:return json.loads(self.cipher.decrypt(row[0])),row[1]
        return {'phase':'INITIAL','cursor':None,'page':None,'threads':{}},0

    def step(self,client):
        from .kernel.policy import enforce_durable_stop
        from .google_policy import ImportPolicy
        if not isinstance(self.policy,ImportPolicy):raise PermissionError("Private import review required")
        self.policy.require(self.owner,"gmail")
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            state,generation=self.load()
            profile=client.get('profile',{})
            if profile.get('emailAddress')!=self.owner:raise PermissionError('OAuth account mismatch')
            if state['cursor'] is None:state['cursor']=str(profile['historyId'])
            params={'maxResults':20}
            if state['page']:params['pageToken']=state['page']
            bounded=state['phase']=='INITIAL' and len(state['threads'])+20>THREAD_CAP
            if bounded:
                # Bounded initial coverage: the newest threads up to the cap are held; older mail is NOT covered and the
                # receipt says so. Incremental updates continue from the cursor taken before the initial listing began.
                page={'threads':[],'nextPageToken':None};ids=set()
                state['coverage']={'initial_complete':False,'stopped':'CAPACITY','cap':THREAD_CAP,'order':'newest first'}
            elif state['phase']=='INITIAL':
                page=client.get('threads',params)  # No INBOX-only filter: includes Sent/archives/drafts.
                entries=page.get('threads',[])
                if not isinstance(entries,list) or len(entries)>20:raise ValueError('Page bound exceeded')
                ids={e['id'] for e in entries}
            else:
                params['startHistoryId']=state['cursor']
                try:page=client.get('history',params)
                except GmailError as error:
                    if error.status==404:
                        # No silent full download or cursor advance on expiry.
                        return {'status':'RESYNC_REQUIRED','cursor_preserved':True}
                    raise
                history=page.get('history',[])
                if not isinstance(history,list) or len(history)>20:raise ValueError('History bound exceeded')
                ids=set()
                for entry in history:
                    for msg in entry.get('messages',[]):ids.add(msg['threadId'])
                    for kind in ('messagesAdded','messagesDeleted','labelsAdded','labelsRemoved'):
                        for change in entry.get(kind,[]):ids.add(change['message']['threadId'])
            if len(ids)>20:raise ValueError('Thread refresh bound exceeded; cursor unchanged')
            for tid in sorted(ids):
                if not isinstance(tid,str) or not tid.isalnum() or len(tid)>128:raise ValueError('Invalid thread ID')
                try:thread=client.get('threads/'+tid,{'format':'metadata','metadataHeaders':list(METADATA_HEADERS)})
                except GmailError as error:
                    if error.status==404:state['threads'].pop(tid,None);continue
                    raise
                if thread.get('id')!=tid:raise ValueError('Thread identity mismatch')
                messages=thread.get('messages',[])
                if not messages or len(messages)>200:raise ValueError('Invalid bounded thread')
                seen=set();normalized=[]
                for m in messages:
                    if m['threadId']!=tid or m['id'] in seen:raise ValueError('Inconsistent message identity')
                    seen.add(m['id'])
                    labels=m.get('labelIds',[])
                    if not isinstance(labels,list) or not all(isinstance(x,str) for x in labels):raise ValueError('Invalid labels')
                    date=m['internalDate']
                    if not isinstance(date,str) or not date.isdecimal():raise ValueError('Invalid date')
                    normalized.append({'id':m['id'],'internalDate':date,'labelIds':labels,
                        'headers':minimized_headers(m.get('payload',{})),'source':'gmail-thread:'+tid})
                state['threads'][tid]=sorted(normalized,key=lambda x:(int(x['internalDate']),x['id']))
            evicted=0
            if len(state['threads'])>THREAD_CAP:
                if state['phase']=='INITIAL':raise ValueError('Retention cap of %d threads reached; no silent truncation'%THREAD_CAP)
                # Rolling window (documented policy): keep the newest THREAD_CAP threads; every eviction is counted in the receipt.
                order=sorted(state['threads'],key=lambda t:int(state['threads'][t][-1]['internalDate']) if state['threads'][t] else 0)
                for tid in order[:len(state['threads'])-THREAD_CAP]:state['threads'].pop(tid);evicted+=1
            state['page']=page.get('nextPageToken')
            if state['page'] is not None and (not isinstance(state['page'],str) or len(state['page'])>2048):raise ValueError('Invalid page token')
            if not state['page']:
                if state['phase']=='INCREMENTAL':state['cursor']=str(page['historyId'])
                elif not bounded:state['coverage']={'initial_complete':True,'cap':THREAD_CAP}
                state['phase']='INCREMENTAL'
            encoded=json.dumps(state,allow_nan=False).encode()
            if len(encoded)>STATE_BYTES_CAP:raise ValueError('Encrypted state size bound')
            self.ledger.db.execute('INSERT OR REPLACE INTO google_private_sync VALUES(?,?,?)',
                                  (self.account,self.cipher.encrypt(encoded),generation+1))
            labels=[set(l for m in msgs for l in m['labelIds']) for msgs in state['threads'].values()]
            trace='google-sync-'+self.account[:16]+'-'+str(generation+1)
            receipt={'status':'PAGE_SYNCHRONIZED','phase':state['phase'],'more_pages':bool(state['page']),
                     'thread_count':len(state['threads']),'external_writes':0,'scope':'ENCRYPTED_PERSONAL_METADATA',
                     'trace_id':trace,'generation':generation+1,'threads_refreshed':len(ids),'evicted_oldest':evicted,
                     'cap':THREAD_CAP,'state_bytes':len(encoded),'coverage':state.get('coverage',{'initial_complete':False,'stopped':'IN_PROGRESS'}),
                     'threads_with_inbox':sum('INBOX' in l for l in labels),'threads_with_sent':sum('SENT' in l for l in labels),
                     'cursor_digest':hashlib.sha256(str(state['cursor']).encode()).hexdigest()[:12]}
            self.ledger._append(trace,'decision','personal',receipt)
            return receipt

    def review(self):
        state,_=self.load();items=[]
        for tid,messages in state['threads'].items():
            usable=[m for m in messages if not {'DRAFT','TRASH','SPAM'}.intersection(m['labelIds'])]
            if usable and 'SENT' in usable[-1]['labelIds']:
                items.append({'thread_id':tid,'source':usable[-1]['source'],'message_id':usable[-1]['id'],
                              'status':'OUTGOING_LATEST_NEEDS_REVIEW','resolved_elsewhere':'UNKNOWN',
                              'confidence_method':'DETERMINISTIC_LABEL_AND_TIME_ORDER_NOT_VERIFIED_COMMITMENT'})
        return items
