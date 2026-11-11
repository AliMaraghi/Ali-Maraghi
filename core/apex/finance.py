"""Founder financial accounts: read-only Enable Banking AIS + statement import.

Single existing Ledger; snapshots/sessions Fernet-encrypted; audit receipts carry
counts and provenance only. No payments, transfers or credit applications exist in
this module. A target is LIVE only after an authorized API retrieval receipt;
an imported statement is IMPORTED_STATEMENT, never LIVE.
"""
import csv
import hashlib
import hmac
import json
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode, quote
from cryptography.fernet import Fernet
from .kernel.policy import enforce_durable_stop
from .kernel.schema import strict_json
from .sources.public_http import Connection, resolve_public, LIMIT

HOST = 'api.enablebanking.com'
REDIRECT = 'https://console.apexcorelab.uk/auth/finance/callback'
# Founder-mandated targets. keywords match Enable Banking GB ASPSP names; coverage is
# verified live via GET /aspsps, never assumed. Evidence links record public facts.
TARGETS = (
    {'slug': 'santander', 'name': 'Santander UK', 'kind': 'bank', 'keywords': ('santander',)},
    {'slug': 'hsbc', 'name': 'HSBC UK', 'kind': 'bank', 'keywords': ('hsbc',)},
    {'slug': 'halifax', 'name': 'Halifax', 'kind': 'bank', 'keywords': ('halifax',)},
    {'slug': 'natwest', 'name': 'NatWest', 'kind': 'bank', 'keywords': ('natwest',)},
    {'slug': 'lloyds', 'name': 'Lloyds Bank', 'kind': 'bank', 'keywords': ('lloyds',)},
    {'slug': 'paypal', 'name': 'PayPal', 'kind': 'e-money', 'keywords': ('paypal',),
     'note': 'PayPal UK offers AIS only to FCA-authorised TPPs (developer.paypal.com/docs/psd2-compliance); '
             'reachable only via an aggregator that lists it, else statement import.'},
    {'slug': 'amex', 'name': 'American Express UK', 'kind': 'credit-card', 'keywords': ('american express', 'amex')},
    {'slug': 'capitalone', 'name': 'Capital One UK', 'kind': 'credit-card', 'keywords': ('capital one',)},
    {'slug': 'argospay', 'name': 'Argos Pay', 'kind': 'credit-card', 'keywords': ('argos', 'newday'),
     'note': 'Argos Pay is a NewDay product; NewDay publishes an AIS production API for its card brands '
             '(OBIE NewDay implementation guide). Product-level support must be confirmed at consent.'},
)
BY_SLUG = {t['slug']: t for t in TARGETS}
DAYS = 90
MAX_PAGES = 5


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def minor(amount):
    """Decimal string -> integer minor units; rejects floats/garbage."""
    try:
        value = Decimal(str(amount).replace(',', '').strip())
    except InvalidOperation:
        raise ValueError('Invalid amount') from None
    if not value.is_finite() or abs(value) >= Decimal(10) ** 13:
        raise ValueError('Amount out of bounds')
    return int((value * 100).quantize(Decimal(1)))


def text(value, limit=256):
    if value is None:
        return ''
    if isinstance(value, list):
        value = ' '.join(v for v in value if isinstance(v, str))
    if not isinstance(value, str):
        return ''
    return value.replace('\x00', '')[:limit]


# --- Transport (subprocess-isolated, pinned TLS, fixed operations) -------------

def api_path(op, args):
    if op == 'aspsps':
        return 'GET', '/aspsps?' + urlencode({'country': 'GB', 'psu_type': 'personal'}), None
    if op == 'auth':
        return 'POST', '/auth', {'access': {'valid_until': args['valid_until']},
                                 'aspsp': {'name': args['aspsp'], 'country': 'GB'},
                                 'state': args['state'], 'redirect_url': REDIRECT, 'psu_type': 'personal'}
    if op == 'session':
        return 'POST', '/sessions', {'code': args['code']}
    uid = args.get('uid', '')
    if not re.fullmatch(r'[0-9a-f-]{36}', uid):
        raise ValueError('Invalid account uid')
    if op == 'details':
        return 'GET', '/accounts/' + uid + '/details', None
    if op == 'balances':
        return 'GET', '/accounts/' + uid + '/balances', None
    if op == 'transactions':
        query = {'date_from': args['date_from']}
        if args.get('continuation_key'):
            query['continuation_key'] = args['continuation_key']
        return 'GET', '/accounts/' + uid + '/transactions?' + urlencode(query), None
    if op == 'delete_session':
        return 'DELETE', '/sessions/' + quote(uid), None
    raise ValueError('Unsupported operation')


def fetch(op, jwt_token, **args):
    method, path, body = api_path(op, args)
    if not re.fullmatch(r'[A-Za-z0-9._-]{20,8192}', jwt_token):
        raise ValueError('Invalid application token')
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        headers = {'Authorization': 'Bearer ' + jwt_token, 'Accept': 'application/json',
                   'Accept-Encoding': 'identity', 'Connection': 'close'}
        encoded = None
        if body is not None:
            encoded = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
        conn.request(method, path, encoded, headers)
        response = conn.getresponse()
        raw = response.read(LIMIT + 1)
        if response.status != 200:
            return {'http_status': response.status}  # No upstream body in logs.
        if len(raw) > LIMIT or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise ValueError('Invalid response bounds')
        return {'http_status': 200, 'data': strict_json(raw.decode())}
    finally:
        conn.close()


def call(op, jwt_token, **args):
    try:
        result = subprocess.run([sys.executable, '-B', '-m', 'apex.finance'],
                                input=json.dumps({'op': op, 'jwt_token': jwt_token, **args}).encode(),
                                capture_output=True, timeout=25,
                                env={'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'LANG': 'C.UTF-8'})
        if result.returncode or len(result.stdout) > 2_000_000:
            raise ValueError()
        response = strict_json(result.stdout.decode())
    except Exception:
        raise RuntimeError('Enable Banking transport failed') from None
    if response.get('http_status') != 200 or not isinstance(response.get('data'), dict):
        raise RuntimeError('Enable Banking request rejected: ' + str(response.get('http_status')))
    return response['data']


# --- Normalization ---------------------------------------------------------------

BALANCE_PREFERENCE = ('ITAV', 'CLAV', 'ITBD', 'CLBD', 'OPAV', 'OPBD', 'XPCD', 'VALU', 'OTHR', 'INFO', 'PRCD', 'FWAV')
# Card debt is the booked balance; available amounts describe remaining credit instead.
DEBT_PREFERENCE = ('CLBD', 'ITBD', 'OPBD', 'XPCD', 'VALU', 'OTHR', 'INFO', 'PRCD')


def normalize_balance(data, preference=BALANCE_PREFERENCE):
    balances = data.get('balances')
    if not isinstance(balances, list) or len(balances) > 20:
        raise ValueError('Invalid balances')
    found = {}
    for b in balances:
        kind = b.get('balance_type'); amount = b.get('balance_amount') or {}
        if kind in preference and kind not in found:
            found[kind] = {'type': kind, 'minor': minor(amount.get('amount')), 'currency': text(amount.get('currency'), 3),
                           'reference_date': text(b.get('reference_date'), 32)}
    return next((found[k] for k in preference if k in found), None)


def normalize_transaction(t, source):
    amount = t.get('transaction_amount') or {}
    value = abs(minor(amount.get('amount')))
    indicator = t.get('credit_debit_indicator')
    if indicator not in ('CRDT', 'DBIT'):
        raise ValueError('Missing credit/debit indicator')
    party = t.get('creditor') if indicator == 'DBIT' else t.get('debtor')
    return {'date': text(t.get('booking_date') or t.get('value_date') or t.get('transaction_date'), 10),
            'minor': value if indicator == 'CRDT' else -value, 'currency': text(amount.get('currency'), 3),
            'description': text(t.get('remittance_information')) or text((party or {}).get('name')),
            'status': text(t.get('status'), 8), 'reference': text(t.get('entry_reference') or t.get('transaction_id'), 128),
            'source': source}


def parse_statement(path, fmt):
    """PayPal activity CSV or generic CSV(date,description,amount,currency[,balance])."""
    rows, closing = [], None
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        fields = {f.strip().lower(): f for f in reader.fieldnames or []}
        for index, raw in enumerate(reader):
            if index >= 20000:
                raise ValueError('Statement row bound')
            row = {k.strip().lower(): (v or '').strip() for k, v in raw.items() if k}
            if fmt == 'paypal':
                if row.get('status', '').lower() not in ('completed', ''):
                    continue
                day, month, year = row['date'].split('/')
                date = '%04d-%02d-%02d' % (int(year), int(month), int(day))
                value, currency = minor(row.get('net') or row['gross']), row['currency']
                description = row.get('name') or row.get('type', '')
                reference = row.get('transaction id', '')
                if row.get('balance'):
                    closing = {'minor': minor(row['balance']), 'currency': currency, 'type': 'STATEMENT', 'reference_date': date}
            elif fmt == 'generic':
                date = datetime.strptime(row['date'], '%Y-%m-%d').date().isoformat()
                value, currency, description = minor(row['amount']), row['currency'], row.get('description', '')
                reference = digest(json.dumps(row, sort_keys=True))[:24]
                if row.get('balance'):
                    closing = {'minor': minor(row['balance']), 'currency': currency, 'type': 'STATEMENT', 'reference_date': date}
            else:
                raise ValueError('Unknown statement format')
            if not re.fullmatch(r'[A-Z]{3}', currency):
                raise ValueError('Invalid currency')
            rows.append({'date': date, 'minor': value, 'currency': currency, 'description': text(description),
                         'status': 'BOOK', 'reference': text(reference, 128), 'source': 'statement-import'})
    if not rows:
        raise ValueError('No completed transactions found; check format')
    return rows, closing, sorted(fields)


# --- Ledger-bound service ------------------------------------------------------

class Finance:
    def __init__(self, ledger, key, owner, app_id=None, private_key_pem=None):
        self.ledger, self.cipher, self.owner = ledger, Fernet(key), owner
        self.app_id, self.private_key = app_id, private_key_pem
        if app_id is not None and not re.fullmatch(r'[0-9a-f-]{36}', app_id):
            raise ValueError('Enable Banking application id must be a UUID')
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS finance_pending (state_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL, slug TEXT NOT NULL, aspsp TEXT NOT NULL, expires INTEGER NOT NULL)')
            ledger.db.execute('CREATE TABLE IF NOT EXISTS finance_private (slug TEXT PRIMARY KEY, encrypted BLOB NOT NULL, generation INTEGER NOT NULL)')
            ledger.db.execute('CREATE TABLE IF NOT EXISTS finance_aspsps (singleton INTEGER PRIMARY KEY CHECK(singleton=1), observed_at INTEGER NOT NULL, names TEXT NOT NULL)')

    # Application JWT: RS256, <=1h lifetime (provider maximum 24h).
    def token(self):
        if not self.app_id or not self.private_key:
            raise PermissionError('Enable Banking application not provisioned')
        import jwt
        now = int(time.time())
        return jwt.encode({'iss': 'enablebanking.com', 'aud': 'api.enablebanking.com', 'iat': now, 'exp': now + 3600},
                          self.private_key, algorithm='RS256', headers={'kid': self.app_id})

    def load(self, slug):
        row = self.ledger.db.execute('SELECT encrypted,generation FROM finance_private WHERE slug=?', (slug,)).fetchone()
        return (strict_json(self.cipher.decrypt(row[0]).decode()), row[1]) if row else ({}, 0)

    def save(self, slug, state, generation, receipt):
        encoded = json.dumps(state, allow_nan=False).encode()
        if len(encoded) > 4_000_000:
            raise ValueError('Encrypted finance state bound')
        self.ledger.db.execute('INSERT OR REPLACE INTO finance_private VALUES(?,?,?)', (slug, self.cipher.encrypt(encoded), generation + 1))
        self.ledger._append('finance-' + slug + '-' + str(generation + 1), 'decision', 'personal', receipt)

    def coverage(self, transport=call, max_age=86400):
        row = self.ledger.db.execute('SELECT observed_at,names FROM finance_aspsps WHERE singleton=1').fetchone()
        if row and row[0] > time.time() - max_age:
            names = json.loads(row[1])
        else:
            data = transport('aspsps', self.token()).get('aspsps')
            if not isinstance(data, list) or len(data) > 2000:
                raise ValueError('Invalid ASPSP list')
            names = sorted({a['name'] for a in data if isinstance(a, dict) and a.get('country') == 'GB'
                            and isinstance(a.get('name'), str) and len(a['name']) <= 128})
            with self.ledger.transaction():
                self.ledger.db.execute('INSERT OR REPLACE INTO finance_aspsps VALUES(1,?,?)', (int(time.time()), json.dumps(names)))
                self.ledger._append('finance-coverage-' + str(int(time.time())), 'evaluation', 'personal',
                                    {'provider': 'enablebanking', 'gb_aspsp_count': len(names)})
        return {t['slug']: [n for n in names if any(k in n.lower() for k in t['keywords'])] for t in TARGETS}

    def begin(self, authenticated_owner, session, slug, index, transport=call):
        if authenticated_owner != self.owner:
            raise PermissionError('Owner required')
        candidates = self.coverage(transport)[BY_SLUG[slug]['slug']]
        if type(index) is not int or not 0 <= index < len(candidates):
            raise PermissionError('Institution not covered by the configured aggregator')
        aspsp = candidates[index]
        state = secrets.token_urlsafe(32); now = int(time.time())
        valid_until = (datetime.now(timezone.utc) + timedelta(days=89)).strftime('%Y-%m-%dT%H:%M:%S.000000+00:00')
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            self.ledger.db.execute('DELETE FROM finance_pending WHERE expires<=?', (now,))
            if self.ledger.db.execute('SELECT count(*) FROM finance_pending').fetchone()[0] >= 10:
                raise ValueError('Pending consent cap')
            self.ledger.db.execute('INSERT INTO finance_pending VALUES(?,?,?,?,?)', (digest(state), digest(session), slug, aspsp, now + 900))
            self.ledger._append('finance-start-' + digest(state)[:24], 'decision', 'personal',
                                {'slug': slug, 'aspsp': aspsp, 'phase': 'PENDING_OWNER_BANK_CONSENT', 'access': 'READ_ONLY_AIS'})
        return transport('auth', self.token(), aspsp=aspsp, state=state, valid_until=valid_until)['url']

    def callback(self, authenticated_owner, session, state, code, transport=call):
        if authenticated_owner != self.owner:
            raise PermissionError('Owner required')
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            row = self.ledger.db.execute('SELECT session_hash,slug,aspsp,expires FROM finance_pending WHERE state_hash=?', (digest(state),)).fetchone()
            if row is None or row[3] <= time.time() or not hmac.compare_digest(row[0], digest(session)):
                raise PermissionError('Invalid, expired or replayed consent state')
            self.ledger.db.execute('DELETE FROM finance_pending WHERE state_hash=?', (digest(state),))
        slug, aspsp = row[1], row[2]
        data = transport('session', self.token(), code=code)
        accounts = data.get('accounts')
        if not isinstance(data.get('session_id'), str) or not isinstance(accounts, list) or len(accounts) > 20:
            raise ValueError('Invalid session response')
        linked = []
        for a in accounts:
            if not isinstance(a, dict) or not isinstance(a.get('uid'), str):
                continue
            limit = a.get('credit_limit') or {}
            linked.append({'uid': a['uid'], 'name': text(a.get('name') or a.get('product'), 128),
                           'currency': text(a.get('currency'), 3), 'type': text(a.get('cash_account_type'), 8),
                           'credit_limit_minor': minor(limit['amount']) if limit.get('amount') is not None else None})
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            state_, generation = self.load(slug)
            state_.update(session_id=data['session_id'], aspsp=aspsp, accounts=linked, consent='AUTHORIZED',
                          valid_until=text((data.get('access') or {}).get('valid_until'), 40), errors=[])
            self.save(slug, state_, generation, {'slug': slug, 'phase': 'CONSENT_AUTHORIZED', 'aspsp': aspsp,
                                                 'account_count': len(linked), 'external_writes': 0})
        return {'slug': slug, 'accounts': len(linked)}

    def sync(self, slug, transport=call):
        """One bounded read-only refresh: details, balance, <=90 days of transactions."""
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            state, generation = self.load(slug)
        if state.get('consent') != 'AUTHORIZED':
            raise PermissionError('Bank consent required')
        token = self.token(); since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).date().isoformat()
        snapshots, errors = [], []
        for account in state['accounts']:
            try:
                card = BY_SLUG[slug]['kind'] == 'credit-card' or account.get('type') == 'CARD'
                balance = normalize_balance(transport('balances', token, uid=account['uid']),
                                            DEBT_PREFERENCE if card else BALANCE_PREFERENCE)
                transactions, key = [], None
                for _ in range(MAX_PAGES):
                    page = transport('transactions', token, uid=account['uid'], date_from=since, continuation_key=key)
                    for t in (page.get('transactions') or [])[:1000]:
                        transactions.append(normalize_transaction(t, 'enablebanking:' + state['aspsp']))
                    key = page.get('continuation_key')
                    if not key:
                        break
                snapshots.append({**account, 'balance': balance, 'transactions': transactions[-2000:], 'complete': not key})
            except RuntimeError as failure:
                errors.append({'account': account['name'], 'error': str(failure)[:120]})
                if '401' in str(failure) or '403' in str(failure):
                    state['consent'] = 'RECONNECT_REQUIRED'
        observed = int(time.time())
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            _, generation = self.load(slug)
            if snapshots:
                state.update(snapshots=snapshots, last_success=observed, source='LIVE_AIS')
            state['errors'] = errors; state['last_attempt'] = observed
            receipt = {'slug': slug, 'phase': 'AIS_RETRIEVAL', 'http_verified_accounts': len(snapshots),
                       'transaction_count': sum(len(s['transactions']) for s in snapshots),
                       'errors': len(errors), 'observed_at': observed, 'external_writes': 0, 'paid_api_spend_pence': 0}
            self.save(slug, state, generation, receipt)
        return receipt

    def import_statement(self, slug, path, fmt):
        if slug not in BY_SLUG:
            raise ValueError('Unknown account')
        rows, closing, columns = parse_statement(path, fmt)
        file_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            state, generation = self.load(slug)
            imported = state.setdefault('imports', [])
            if any(i['sha256'] == file_hash for i in imported):
                return {'slug': slug, 'phase': 'ALREADY_IMPORTED'}
            known = {r['reference'] for i in imported for r in i['rows']}
            fresh = [r for r in rows if r['reference'] not in known]
            imported.append({'sha256': file_hash, 'imported_at': int(time.time()), 'format': fmt, 'rows': fresh, 'closing': closing})
            receipt = {'slug': slug, 'phase': 'STATEMENT_IMPORTED', 'rows': len(fresh), 'duplicates_skipped': len(rows) - len(fresh),
                       'file_sha256': file_hash, 'columns': columns[:20], 'live_connection': False}
            self.save(slug, state, generation, receipt)
        return receipt

    def disconnect(self, slug, transport=call):
        with self.ledger.transaction():
            state, generation = self.load(slug)
        if state.get('session_id'):
            try:
                transport('delete_session', self.token(), uid=state['session_id'])
            except (RuntimeError, PermissionError, ValueError):
                pass  # Local revocation still applies; bank-side consent can be revoked in the bank app.
        with self.ledger.transaction():
            _, generation = self.load(slug)
            state.update(consent='REVOKED', session_id=None)
            self.save(slug, state, generation, {'slug': slug, 'phase': 'LOCALLY_DISCONNECTED'})

    # --- Projection for the founder dashboard ------------------------------------
    def dashboard(self, now=None):
        now = int(time.time()) if now is None else now
        entries, totals = [], {'assets_minor': 0, 'liabilities_minor': 0, 'income_30d_minor': 0, 'spending_30d_minor': 0}
        cutoff = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=30)).date().isoformat()
        for target in TARGETS:
            state, _ = self.load(target['slug'])
            live = state.get('source') == 'LIVE_AIS' and state.get('last_success')
            imports = state.get('imports', [])
            if live and state.get('consent') == 'AUTHORIZED':
                status = 'LIVE'
            elif state.get('consent') in ('RECONNECT_REQUIRED', 'REVOKED'):
                status = state['consent']
            elif state.get('consent') == 'AUTHORIZED':
                status = 'AUTHORIZED_NOT_YET_SYNCED'
            elif imports:
                status = 'IMPORTED_STATEMENT'
            else:
                status = 'NOT_CONNECTED'
            accounts = []
            for snap in state.get('snapshots', []) if live else []:
                balance = snap.get('balance') or {}
                liability = target['kind'] == 'credit-card' or snap.get('type') == 'CARD'
                value = balance.get('minor')
                if value is not None and balance.get('currency') == 'GBP':
                    if liability:
                        # ASPSP sign conventions differ for card debt; magnitude of booked balance.
                        totals['liabilities_minor'] += abs(value)
                    else:
                        totals['assets_minor'] += max(value, 0)
                for t in snap['transactions']:
                    if t['date'] >= cutoff and t['currency'] == 'GBP':
                        totals['income_30d_minor' if t['minor'] > 0 else 'spending_30d_minor'] += abs(t['minor'])
                accounts.append({'name': snap['name'], 'type': snap.get('type'), 'balance': balance,
                                 'credit_limit_minor': snap.get('credit_limit_minor'), 'transactions': len(snap['transactions']),
                                 'liability': liability, 'payment_due_date': None})
            for item in imports:
                accounts.append({'name': 'Imported statement ' + item['sha256'][:8], 'type': 'STATEMENT',
                                 'balance': item.get('closing'), 'transactions': len(item['rows']),
                                 'liability': target['kind'] == 'credit-card', 'payment_due_date': None, 'provenance': 'statement-import'})
            entries.append({'slug': target['slug'], 'name': target['name'], 'kind': target['kind'], 'status': status,
                            'aspsp': state.get('aspsp'), 'consent_valid_until': state.get('valid_until'),
                            'last_success': state.get('last_success'), 'last_attempt': state.get('last_attempt'),
                            'errors': state.get('errors', []), 'accounts': accounts, 'note': target.get('note')})
        return {'entries': entries, 'totals_gbp': totals, 'live_count': sum(e['status'] == 'LIVE' for e in entries),
                'payment_due_dates': 'NOT_SUPPLIED_BY_AIS_BALANCE_TRANSACTION_ENDPOINTS',
                'scope': 'READ_ONLY; LIVE requires authorized retrieval receipt; imports are not live connections'}


if __name__ == '__main__':
    try:
        args = strict_json(sys.stdin.buffer.read(65537).decode())
        print(json.dumps(fetch(**args), allow_nan=False))
    except Exception:
        print('{"http_status":0}')
