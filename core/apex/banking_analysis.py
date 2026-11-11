"""Private projections of existing encrypted TrueLayer receipts.

No network, financial advice, forecasting or invented transaction schema. Returned
values are personal data: expose only through an authenticated owner boundary.
"""
from datetime import datetime, timezone
import re
from .banking import BankingClient, utc
from .kernel.policy import enforce_durable_stop
from .kernel.schema import identifier, strict_json


def currency(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{3}', value):
        raise ValueError('Invalid ISO currency shape')
    return value


def amount(value):
    if type(value) is not int or abs(value) > 2**63-1:
        raise ValueError('Bounded integer minor units required')
    return value


def normalize(operation, data):
    if not isinstance(data, dict): raise ValueError('Expected bank object')
    if operation == 'balance':
        result = {'currency':currency(data.get('currency')),
                  'current_balance_in_minor':amount(data.get('current_balance_in_minor'))}
        for field in ('available_balance_in_minor','overdraft_in_minor'):
            if field in data: result[field]=amount(data[field])
        return {'kind':'BALANCE','data':result,
                'limitations':['Available balance may include overdraft; not earned income.',
                               'Current balance excludes pending transactions.']}
    if operation == 'accounts':
        items=data.get('items'); pagination=data.get('pagination')
        if not isinstance(items,list) or len(items)>50 or not isinstance(pagination,dict):
            raise ValueError('Invalid bounded accounts page')
        counts={}; seen=set()
        for item in items:
            if not isinstance(item,dict): raise ValueError('Invalid account')
            account=item.get('id')
            if not isinstance(account,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',account) or account in seen:
                raise ValueError('Invalid or duplicate account')
            seen.add(account)
            if item.get('type') not in {'account','card'}: raise ValueError('Invalid account kind')
            curr=currency(item.get('currency')); counts[curr]=counts.get(curr,0)+1
        cursor=pagination.get('next_cursor')
        if cursor is not None and (not isinstance(cursor,str) or not 1<=len(cursor)<=4096):
            raise ValueError('Invalid pagination cursor')
        return {'kind':'ACCOUNT_COUNTS','data':{'count':len(items),'counts_by_currency':counts},
                'coverage':'BOUNDED_PAGE_NOT_COMPLETE_INVENTORY',
                'limitations':['Provider documents maximum 50 accounts and inactive account pagination.']}
    if operation in {'transactions_start','transactions_poll'}:
        return {'kind':'TRANSACTIONS','status':'BLOCKED_SCHEMA',
                'limitations':['Nested v3 transaction schema has not been verified; no spending or cash-flow inference.']}
    raise ValueError('Unknown banking operation')


def receipt_projection(client, request_key, now=None):
    """Read one authorized encrypted receipt without refreshing it or exporting raw data."""
    if not isinstance(client,BankingClient): raise TypeError('Existing BankingClient required')
    identifier(request_key)
    client._require(); enforce_durable_stop(client.ledger)
    now=now or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None: raise ValueError('Aware clock required')
    row=client.ledger.db.execute('SELECT encrypted FROM banking_private_receipts WHERE subject=? AND request_key=?',
                                (client.subject,request_key)).fetchone()
    if row is None:return {'status':'NO_RECEIPT','request_key':request_key}
    saved=strict_json(client.cipher.decrypt(row[0]).decode())
    observed=utc(saved['observed_at']); age=(now-observed).total_seconds()
    if age<0: raise ValueError('Receipt observed in future')
    source={'request_key':request_key,'request_digest':saved['request_digest'],
            'observed_at':saved['observed_at'],'age_seconds':int(age),
            'freshness':'STALE' if age>86400 else 'WITHIN_24H_NOT_CURRENT_HEALTH'}
    if saved['http_status']!=200 or saved['state']!='RECEIVED_UNVALIDATED':
        return {'status':'NO_VALIDATED_DATA','source':source,'http_status':saved['http_status']}
    result=normalize(saved['operation'],saved['data'])
    return {'status':result.pop('status','SCHEMA_VALIDATED_HISTORICAL'),
            'source':source,'privacy':'PERSONAL_OWNER_ONLY',
            'verification':'STRUCTURE_ONLY_NOT_INDEPENDENT_BANK_VERIFICATION',**result}
