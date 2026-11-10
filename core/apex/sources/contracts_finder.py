"""One bounded Contracts Finder public GET; no accounts, contacts or bid actions.

The parent process enforces a hard timeout including DNS, TLS and response reads.
Transport connects to an already validated IP while retaining HTTPS hostname
verification. Proxy environment, cookies and redirects to other hosts are unused.
"""
from datetime import date, datetime, timezone
import base64
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from apex.kernel.schema import strict_json, timestamp
from apex.kernel.policy import KillState

HOST = 'www.contractsfinder.service.gov.uk'
PATH = '/Published/Notices/OCDS/Search'
LIMIT = 1_048_576
PAGE_SIZE = 5
TIMEOUT = 15
LICENCE = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'


class SourceError(ValueError):
    """Only developer-defined messages; never include remote body content."""



def search_url(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a.isoformat() != start or b.isoformat() != end or not 0 <= (b-a).days <= 31:
        raise SourceError('Date window must be ISO dates and at most 31 days')
    return 'https://' + HOST + PATH + '?' + urlencode({
        'publishedFrom': start, 'publishedTo': end, 'size': PAGE_SIZE,
        'page': 1, 'orderBy': 'publishedDate', 'order': 'DESC'})


def validate_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.netloc != HOST or p.path != PATH
            or p.fragment or len(url) > 2048 or any(ord(c) <= 32 for c in url)):
        raise SourceError('Destination outside fixed public-source scope')
    q = parse_qs(p.query, strict_parsing=True)
    expected = {'publishedFrom', 'publishedTo', 'size', 'page', 'orderBy', 'order'}
    if set(q) != expected or any(len(v) != 1 for v in q.values()):
        raise SourceError('Invalid source query')
    canonical = search_url(q['publishedFrom'][0], q['publishedTo'][0])
    if parse_qs(urlsplit(canonical).query) != q:
        raise SourceError('Query changes source or page budget')
    return p


def resolve_public(host):
    answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = []
    for family, _, _, _, sockaddr in answers:
        address = ipaddress.ip_address(sockaddr[0])
        if (family not in {socket.AF_INET, socket.AF_INET6} or not address.is_global
                or address.is_multicast or address.is_reserved
                or getattr(address, 'ipv4_mapped', None) is not None):
            raise SourceError('DNS contains a prohibited address')
        addresses.append((family, str(address)))
    if not addresses:
        raise SourceError('DNS returned no destination')
    return sorted(set(addresses))[0]  # One attempt; no address failover/retries.


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, family, address):
        super().__init__(HOST, timeout=5, context=ssl.create_default_context())
        self.family, self.address = family, address

    def connect(self):
        raw = socket.socket(self.family, socket.SOCK_STREAM)
        try:
            raw.settimeout(5)
            raw.connect((self.address, 443))
            if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(self.address):
                raise SourceError('Peer differs from validated destination')
            self.sock = self._context.wrap_socket(raw, server_hostname=HOST)
        except BaseException:
            raw.close()
            raise


def fetch_page(url):
    """Worker-only transport. Call collect() for authority and hard timeout."""
    hops = []
    for hop in range(2):  # At most one redirect, revalidate and re-resolve each.
        p = validate_url(url)
        family, address = resolve_public(HOST)
        conn = PinnedHTTPS(family, address)
        try:
            conn.request('GET', p.path + '?' + p.query, headers={
                'Accept': 'application/json', 'Accept-Encoding': 'identity',
                'User-Agent': 'APEX-Development-PublicResearch/0.1', 'Connection': 'close'})
            response = conn.getresponse()
            hops.append({'url': url, 'peer_ip': address, 'status': response.status})
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader('Location')
                if hop or not location:
                    raise SourceError('Redirect limit or missing destination')
                target = urljoin(url, location)
                validate_url(target)
                # Redirects may normalize encoding, never change the query scope.
                if parse_qs(urlsplit(target).query) != parse_qs(p.query):
                    raise SourceError('Redirect changes query scope')
                url = target
                continue
            if response.status != 200:
                raise SourceError('PUBLIC_SOURCE_HTTP_' + str(response.status))
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise SourceError('Compressed responses unsupported')
            if response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise SourceError('Expected JSON response')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > LIMIT):
                raise SourceError('Invalid or oversized response length')
            body = response.read(LIMIT + 1)
            if len(body) > LIMIT or (length is not None and len(body) != int(length)):
                raise SourceError('Response truncated or oversized')
            return {'body_b64': base64.b64encode(body).decode(), 'hops': hops,
                    'retrieved_at': datetime.now(timezone.utc).isoformat()}
        finally:
            conn.close()
    raise SourceError('No response')


def parse_packet(body, requested_url, retrieved_at):
    """Minimize retained data. No contact details or document URLs are returned."""
    validate_url(requested_url)
    retrieved = timestamp(retrieved_at)
    if len(body) > LIMIT:
        raise SourceError('Packet too large')
    data = strict_json(body.decode('utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('releases'), list):
        raise SourceError('Unknown source schema')
    releases = data['releases']
    if len(releases) > PAGE_SIZE:
        raise SourceError('Server exceeded requested page size')
    total = data.get('hitsCount')
    if type(total) is not int or total < len(releases):
        raise SourceError('Missing or invalid total count')
    notices, seen = [], set()
    def string(value, field, maximum=300):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise SourceError('Invalid notice ' + field)
        if any(ord(c) < 32 for c in value):
            raise SourceError('Control character in notice field')
        return value
    for release in releases:
        if not isinstance(release, dict):
            raise SourceError('Invalid release')
        rid, ocid = string(release.get('id'), 'id'), string(release.get('ocid'), 'ocid')
        if (ocid, rid) in seen:
            raise SourceError('Duplicate release identity')
        seen.add((ocid, rid))
        published = timestamp(release.get('date'))
        if published > retrieved:
            raise SourceError('Future notice timestamp')
        window = parse_qs(urlsplit(requested_url).query)
        if not date.fromisoformat(window['publishedFrom'][0]) <= published.date() <= date.fromisoformat(window['publishedTo'][0]):
            raise SourceError('Notice outside requested date window')
        tender = release.get('tender', {})
        if not isinstance(tender, dict):
            raise SourceError('Invalid tender')
        status = tender.get('status', 'unknown')
        if status not in {'planning', 'planned', 'active', 'cancelled', 'unsuccessful', 'complete', 'withdrawn', 'unknown'}:
            raise SourceError('Unknown tender status')
        tags = release.get('tag', [])
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or len(t) > 60 for t in tags):
            raise SourceError('Invalid tags')
        period = tender.get('tenderPeriod', {})
        if not isinstance(period, dict):
            raise SourceError('Invalid tender period')
        deadline = period.get('endDate')
        closed = timestamp(deadline) <= retrieved if deadline is not None else None
        objections = []
        if status != 'active': objections.append('NOT_ACTIVE_TENDER')
        if closed is True: objections.append('DEADLINE_PASSED')
        if deadline is None: objections.append('DEADLINE_UNKNOWN')
        if any(tag.startswith(('award', 'contract')) for tag in tags): objections.append('AWARD_OR_CONTRACT_STAGE')
        notices.append({'ocid': ocid, 'release_id': rid, 'published_at': release['date'],
                        'status': status, 'tags': tags, 'deadline': deadline,
                        'disconfirming_flags': objections,
                        'capture_feasibility': 'UNVERIFIED', 'verified_customer_demand': False})
    return {'schema': 'apex.public-procurement.v1', 'source_url': requested_url,
            'adapter_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'retrieved_at': retrieved_at, 'response_sha256': hashlib.sha256(body).hexdigest(),
            'response_bytes': len(body), 'raw_response_retained': False,
            'retained_fields': 'release identity, dates, status and stage only; contact/title/description omitted',
            'notices': notices, 'observed_items': len(notices), 'server_reported_total': total,
            'pages_fetched': 1, 'pages_followed_automatically': 0,
            'coverage': 'One page from one registry, not all procurement or market demand',
            'independence_groups': 1, 'licence_url': LICENCE,
            'licence_verified_for_current_endpoint': False,
            'proposed_attribution': 'Contains public sector information licensed under the Open Government Licence v3.0.',
            'actions_executed': [], 'paid_api_spend_pence': 0,
            'limitations': ['Buyer assertions are not independently verified.',
                           'Tender value is not founder income; eligibility and delivery cost are unknown.',
                           'Open status alone does not establish an actionable opportunity.']}


def collect(start, end, *, network_authorized=False, kill_state=KillState.RUNNING):
    if network_authorized is not True or kill_state is not KillState.RUNNING:
        raise PermissionError('Explicit public retrieval authority and RUNNING state required')
    url = search_url(start, end)
    core = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', '-m', 'apex.sources.contracts_finder', url],
                            capture_output=True, timeout=TIMEOUT, check=False,
                            env={'PYTHONPATH': str(core), 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'})
    if result.returncode != 0:
        # Worker never prints raw response/exception content or credentials.
        raise SourceError('PUBLIC_FETCH_FAILED: ' + result.stdout.decode('ascii', errors='replace')[:160])
    if len(result.stdout) > 1_500_000:
        raise SourceError('Worker output exceeds limit')
    envelope = strict_json(result.stdout.decode())
    body = base64.b64decode(envelope['body_b64'], validate=True)
    packet = parse_packet(body, url, envelope['retrieved_at'])
    packet['transport_hops'] = envelope['hops']
    return packet


if __name__ == '__main__':
    try:
        print(json.dumps(fetch_page(sys.argv[1]), allow_nan=False))
    except Exception as error:
        code = str(error) if str(error).startswith('PUBLIC_SOURCE_HTTP_') else type(error).__name__
        print(json.dumps({'status': 'BLOCKED', 'reason': code}))
        sys.exit(2)
