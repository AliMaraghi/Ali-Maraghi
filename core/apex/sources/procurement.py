"""Official Find a Tender OCDS and TED v3 search contracts (reviewed 2026-11-10).

Public metadata only. A notice is a buyer assertion, never verified founder fit.
No contact extraction, document following, bids or credentials. Search scope is
provided by the operator; no fixed industry/country ontology.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import base64
import hashlib
import re
from urllib.parse import urlencode

from apex.kernel.schema import strict_json, timestamp
from .public_http import retrieve, LIMIT
from .contracts_finder import SourceError

FTS = 'https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages'
TED = 'https://api.ted.europa.eu/v3/notices/search'
OGL = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'
TED_TERMS = 'https://ted.europa.eu/en/legal-notice'
TED_FIELDS = ['publication-number', 'notice-title', 'publication-date',
              'buyer-country', 'classification-cpv', 'notice-type',
              'deadline-receipt-tender-date-lot']


def text(value, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise SourceError('Invalid bounded public field')
    return value


def request(spec):
    if not isinstance(spec, dict):
        raise SourceError('Source request must be an object')
    source = spec.get('source')
    if source == 'fts' and set(spec) == {'source', 'notice'}:
        notice = spec['notice']
        if not isinstance(notice, str) or not re.fullmatch(r'[0-9]{6}-[0-9]{4}', notice):
            raise SourceError('Invalid notice ID')
        return FTS + '/' + notice, 'GET', None
    if source == 'fts' and set(spec) == {'source', 'date'}:
        day = date.fromisoformat(spec['date'])
        if day.isoformat() != spec['date']:
            raise SourceError('ISO date required')
        return FTS + '?' + urlencode({'limit': 5, 'updatedFrom': day.isoformat()+'T00:00:00',
            'updatedTo': day.isoformat()+'T23:59:59'}), 'GET', None
    if source == 'ted' and set(spec) == {'source', 'query'}:
        query = text(spec['query'], 600)
        return TED, 'POST', {'query': query, 'fields': TED_FIELDS, 'limit': 5,
            'page': 1, 'scope': 'ALL', 'onlyLatestVersions': True, 'paginationMode': 'PAGE_NUMBER'}
    raise SourceError('Unsupported source or request fields; adapter review required')


def money(value):
    if value is None:
        return None
    # Source decimals are represented as strings; never use them as spend authority.
    if type(value) not in {str, int, float} or isinstance(value, bool):
        raise SourceError('Invalid monetary value')
    try:
        d = Decimal(str(value))
    except InvalidOperation as e:
        raise SourceError('Invalid monetary value') from e
    if not d.is_finite() or d < 0 or d > Decimal('1e15') or d.as_tuple().exponent < -4:
        raise SourceError('Invalid finite monetary bound')
    return str(d)


def parse_fts(data, spec, captured):
    if not isinstance(data, dict) or not isinstance(data.get('releases'), list):
        raise SourceError('Unknown OCDS release package')
    licence = data.get('license', '').replace('http://', 'https://')
    if licence != OGL:
        raise SourceError('Unreviewed package licence')
    releases = data['releases']
    if len(releases) > 5:
        raise SourceError('Release count exceeds bounded request')
    rows, seen = [], set()
    for r in releases:
        rid, ocid = text(r['id'], 120), text(r['ocid'], 120)
        if not re.fullmatch(r'[0-9]{6}-[0-9]{4}', rid) or not re.fullmatch(r'ocds-h6vhtk-[0-9a-f]{6}', ocid):
            raise SourceError('Unexpected official identity')
        if 'notice' in spec and rid != spec['notice']:
            raise SourceError('Response is not requested notice')
        if (ocid, rid) in seen:
            raise SourceError('Duplicate release')
        seen.add((ocid, rid))
        published = timestamp(r['date'])
        if published > captured:
            raise SourceError('Future release')
        t = r.get('tender', {})
        deadline = t.get('tenderPeriod', {}).get('endDate')
        flags = []
        if deadline is None: flags.append('DEADLINE_UNKNOWN')
        elif timestamp(deadline) <= captured: flags.append('DEADLINE_PASSED')
        status = text(t.get('status', 'unknown'), 30)
        if status != 'active': flags.append('NOT_ACTIVE_TENDER')
        tags = r.get('tag', [])
        if not isinstance(tags, list) or len(tags) > 20: raise SourceError('Invalid stage tags')
        if any(text(v, 60).startswith(('award','contract')) for v in tags): flags.append('AWARD_OR_CONTRACT_STAGE')
        value = t.get('value', {})
        amount = money(value.get('amount'))
        currency = text(value.get('currency', 'UNKNOWN'), 10)
        rows.append({'record_id': rid, 'ocid': ocid, 'title': text(t.get('title', 'Title unavailable')),
            'buyer': text(r.get('buyer', {}).get('name', 'UNKNOWN')),
            'country': 'GBR', 'cpv': t.get('classification', {}).get('id'),
            'source_url': 'https://www.find-tender.service.gov.uk/Notice/'+rid,
            'source_time': r['date'], 'deadline': deadline, 'deadline_authority': 'NOTICE_ONLY_PORTAL_UNCHECKED',
            'headline_value': amount, 'currency': currency, 'status': status,
            'disconfirming_flags': flags, 'seed_origin': 'FOUNDER_MANUAL_RESEARCH' if 'notice' in spec else 'BOUNDED_API_SCAN'})
    return rows, None  # No invented total from this release package.


def parse_ted(data, captured):
    if not isinstance(data, dict) or not isinstance(data.get('notices'), list) or data.get('timedOut') is True:
        raise SourceError('Invalid or incomplete TED search')
    rows = data['notices']
    total = data.get('totalNoticeCount')
    if len(rows) > 5 or type(total) is not int or total < len(rows):
        raise SourceError('Invalid exact TED coverage count')
    result, seen = [], set()
    for r in rows:
        rid = text(r['publication-number'], 40)
        if not re.fullmatch(r'[0-9]{1,6}-[0-9]{4}', rid) or rid in seen:
            raise SourceError('Invalid or duplicate TED identity')
        seen.add(rid)
        titles = r.get('notice-title', {})
        if not isinstance(titles, dict) or len(titles) > 30: raise SourceError('Invalid multilingual title')
        title = titles.get('eng') or next(iter(titles.values()), 'Title unavailable')
        # Date-only field does not establish an exact submission time or timezone.
        published = text(r['publication-date'], 40)
        pd = date.fromisoformat(published[:10])
        if pd > captured.date(): raise SourceError('Future TED publication')
        fields = {}
        for key in ['buyer-country','classification-cpv','notice-type','deadline-receipt-tender-date-lot']:
            values = r.get(key, [])
            if not isinstance(values, list) or len(values) > 100: raise SourceError('Invalid TED array')
            fields[key] = [text(v, 100) for v in values]
        flags = ['PORTAL_DEADLINE_UNVERIFIED', 'ELIGIBILITY_UNKNOWN']
        if any(v.startswith(('can-', 'veat')) for v in fields['notice-type']): flags.append('AWARD_OR_CONTRACT_STAGE')
        result.append({'record_id': rid, 'title': text(title), 'buyer': 'UNKNOWN_NOT_REQUESTED',
            'country': fields['buyer-country'], 'cpv': fields['classification-cpv'],
            'source_url': 'https://ted.europa.eu/en/notice/-/detail/'+rid,
            'source_time': published, 'deadline': fields['deadline-receipt-tender-date-lot'],
            'deadline_authority': 'DATE_ONLY_PORTAL_UNCHECKED', 'headline_value': None,
            'currency': 'UNKNOWN', 'status': fields['notice-type'], 'disconfirming_flags': flags,
            'seed_origin': 'BOUNDED_API_SEARCH'})
    return result, total


def collect(spec):
    """Internal adapter, invoked only through the field gateway's durable stop lock."""
    url, method, body = request(spec)
    envelope = retrieve(url, method, body)
    raw = base64.b64decode(envelope.pop('body_b64', ''), validate=True)
    observation = {**envelope, 'source': spec['source'], 'source_url': url, 'request': spec,
        'publisher': 'Cabinet Office' if spec['source']=='fts' else 'EU Publications Office',
        'allowed_license': OGL if spec['source']=='fts' else TED_TERMS,
        'licence_review_date': '2026-11-10', 'privacy_scope': 'public_procurement_metadata_only',
        'verification_method': 'DNS_all_addresses_IP_pinned_TLS_and_strict_schema',
        'independent_corroboration': 'NOT_PERFORMED', 'records': [],
        'retrieval_status': 'BLOCKED_EXTERNAL_FETCH', 'paid_cost_pence': 0}
    if envelope.get('error'):
        return observation
    if len(raw) > LIMIT or hashlib.sha256(raw).hexdigest() != envelope['sha256']:
        raise SourceError('Response digest or size mismatch')
    if envelope.get('content_type', '').split(';')[0] not in {'application/json','text/json'}:
        observation['error'] = 'NON_JSON_RESPONSE'
        return observation
    try:
        captured = timestamp(envelope['retrieved_at'])
        data = strict_json(raw.decode())
        records, total = parse_fts(data, spec, captured) if spec['source']=='fts' else parse_ted(data, captured)
        observation.update(records=records, observed_count=len(records), server_reported_total=total,
            expiry=(captured+timedelta(hours=24)).isoformat(), retrieval_status='OBSERVED_UNCORROBORATED',
            coverage='One bounded response; no pagination or claim of complete market coverage')
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        observation['error'] = 'SCHEMA_REJECTED_' + type(error).__name__
    return observation
