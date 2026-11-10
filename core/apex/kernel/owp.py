"""Bounded OWP preparation and snapshot coverage; no retrieval or action adapter.

Adapted concepts from the founder's Apex Epoch kit, not its runtime. Arbitrary
lawful search axes are accepted; enumerating them does not discover demand.
"""
from datetime import datetime, timezone
import hashlib
import json

from .evidence import public_uri, read_local
from .policy import Action, Policy
from .schema import fields, identifier, items, strict_json, text, timestamp


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def bounded_int(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid ' + name)
    return value


def label(value, name):
    return ' '.join(text(value, name, 240).split())


def plan_search(request: dict, policy: Policy, now=None) -> dict:
    """Compile a finite, explicit search scope. Caller cannot enable connectors.

    Accept lists rather than arbitrary iterators: even infinite repeated axes
    cannot bypass an output limit. Validate the entire input before truncation.
    """
    d = fields(request, {'task_id', 'expires_at', 'axes', 'sources',
                         'max_probes', 'paid_budget_pence'})
    task_id = identifier(d['task_id'])
    now = now or datetime.now(timezone.utc)
    if timestamp(d['expires_at']) <= now:
        raise ValueError('Expired search task')
    bounded_int(d['paid_budget_pence'], 'paid budget', 0, 0)
    cap = bounded_int(d['max_probes'], 'probe limit', 1, 128)
    allowed, reason = policy.authorize(Action(task_id, 'record_decision', 'opportunity'))
    if not allowed:
        raise PermissionError(reason)
    axes = []
    for value in items(d['axes'], 'axes', 32):
        axis = fields(value, {'geography', 'industry', 'mechanism', 'customer_problem'})
        normalized = {k: label(v, k) for k, v in axis.items()}
        if normalized not in axes:
            axes.append(normalized)
    sources = []
    ids = set()
    for value in items(d['sources'], 'sources', 32):
        source = fields(value, {'id', 'family', 'uri', 'access_note'})
        sid = identifier(source['id'])
        if sid in ids:
            raise ValueError('Duplicate source identifier')
        ids.add(sid)
        uri = text(source['uri'], 'source URI', 2048)
        if not public_uri(uri):
            raise ValueError('Invalid public source URI')
        sources.append({'id': sid, 'family': label(source['family'], 'family'),
                        'uri': uri, 'access_note': label(source['access_note'], 'access note'),
                        'adapter_status': 'BLOCKED_NO_RETRIEVAL_ADAPTER',
                        'rights_verified': False, 'network_authorized': False})
    if not axes or not sources:
        raise ValueError('Explicit axes and source candidates required')
    probes = []
    # Round-robin across axes before advancing source families. Report omissions.
    for source in sources:
        for axis in axes:
            if len(probes) < cap:
                payload = {'axis': axis, 'source_id': source['id'],
                           'source_uri': source['uri'], 'family': source['family']}
                probes.append({'id': 'owp-' + digest(payload)[:32], **payload,
                               'status': 'UNEXECUTED_SEARCH_PROBE'})
    scope = {'axes': axes, 'sources': sources}
    return {'schema': 'apex.owp.plan.v1', 'task_id': task_id, 'domain': 'opportunity',
            'status': 'PREPARATION_ONLY', 'request_sha256': digest(d),
            'scope_sha256': digest(scope), **scope, 'probes': probes,
            'candidate_pairs': len(axes) * len(sources),
            'omitted_pairs': len(axes) * len(sources) - len(probes),
            'open_world_coverage_established': False, 'demand_verified': False,
            'paid_budget_pence': 0, 'actions_executed': [],
            'missing_evidence': ['lawful connector and destination enforcement',
                                 'dated demand and competitor observations',
                                 'capture constraints and disconfirming evidence'],
            'next_step': 'Review source rights and acquire a bounded public snapshot through an authorized adapter.'}


def inspect_coverage(record: dict, root, now=None) -> dict:
    """Compare declared inspected/selected IDs to a bounded local snapshot.

    Snapshot format is a JSON list of unique item IDs. This verifies membership,
    not that a human inspected the items or that the snapshot covers a market.
    """
    d = fields(record, {'search_id', 'source_uri', 'scope', 'artifact', 'sha256',
                        'queried_at', 'expires_at', 'observed_items',
                        'inspected_ids', 'selected_ids', 'synthetic'})
    sid = identifier(d['search_id'])
    scope = label(d['scope'], 'scope')
    source_uri = text(d['source_uri'], 'source URI', 2048)
    if type(d['synthetic']) is not bool or not public_uri(source_uri):
        raise ValueError('Invalid source classification or URI')
    now = now or datetime.now(timezone.utc)
    queried, expires = timestamp(d['queried_at']), timestamp(d['expires_at'])
    if queried > now or expires <= now or expires <= queried:
        raise ValueError('Stale or future coverage')
    observed = bounded_int(d['observed_items'], 'observed count', 0, 10000)
    data = read_local(root, text(d['artifact'], 'artifact'))
    actual = hashlib.sha256(data).hexdigest()
    if d['sha256'] != actual:
        raise ValueError('Snapshot digest mismatch')
    snapshot = [identifier(v) for v in items(strict_json(data.decode()), 'snapshot', 10000)]
    inspected = [identifier(v) for v in items(d['inspected_ids'], 'inspected IDs', 10000)]
    selected = [identifier(v) for v in items(d['selected_ids'], 'selected IDs', 10000)]
    if any(len(x) != len(set(x)) for x in (snapshot, inspected, selected)):
        raise ValueError('Duplicate coverage item')
    if len(snapshot) != observed or not set(selected) <= set(inspected) <= set(snapshot):
        raise ValueError('Coverage counts or membership mismatch')
    return {'schema': 'apex.owp.coverage.v1', 'search_id': sid, 'scope': scope,
            'source_uri': source_uri, 'queried_at': d['queried_at'],
            'expires_at': d['expires_at'], 'snapshot_sha256': actual,
            'record_sha256': digest(d), 'synthetic': d['synthetic'],
            'observed_items': observed, 'inspected_items': len(inspected),
            'selected_items': len(selected), 'uninspected_items': observed - len(inspected),
            'snapshot_fully_inspected_declared': bool(observed and len(inspected) == observed),
            'inspection_independently_verified': False,
            'market_coverage_verified': False, 'unmet_demand_verified': False,
            'limitation': 'Snapshot membership is checked; selection, inspection and source completeness remain unverified.'}
