"""Verify the pinned founder ZIP; optionally reproduce rejected reference defects.

No extraction, network, accounts or services. Reference probes use memory-only
SQLite and run only after all extracted file hashes match the pinned archive.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / 'APEX_EPOCH_ENGINEERING_V1.zip'
PREFIX = 'APEX_EPOCH_ENGINEERING_V1/'
EXPECTED = '611ff49f1e68e33e0e1f69fafb464ae9ea382b1d03ced4c5e6add497913a4a67'


def verify():
    actual = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    if actual != EXPECTED:
        raise ValueError('Unexpected review archive bytes')
    with zipfile.ZipFile(ZIP) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(names) != 48 or len(set(names)) != len(names):
            raise ValueError('Archive file count or duplicate name mismatch')
        for i in infos:
            p = PurePosixPath(i.filename)
            if (p.is_absolute() or '..' in p.parts or not i.filename.startswith(PREFIX)
                    or stat.S_ISLNK(i.external_attr >> 16) or i.file_size > 1_000_000):
                raise ValueError('Unsafe archive entry')
        if z.testzip() is not None:
            raise ValueError('CRC failure')
        checks = {}
        for line in z.read(PREFIX + 'PACKAGE_SHA256SUMS.txt').decode().splitlines():
            checksum, name = line.split(maxsplit=1)
            name = name.lstrip('*')
            if name.startswith('./'):
                name = name[2:]
            if name in checks:
                raise ValueError('Duplicate checksum entry')
            checks[name] = checksum
        if set(checks) != {n[len(PREFIX):] for n in names} - {'PACKAGE_SHA256SUMS.txt'}:
            raise ValueError('Checksum manifest coverage mismatch')
        entries = []
        for n in sorted(names):
            raw = z.read(n); short = n[len(PREFIX):]
            checksum = hashlib.sha256(raw).hexdigest()
            if short in checks and checks[short] != checksum:
                raise ValueError('Checksum mismatch: ' + short)
            entries.append({'path': short, 'bytes': len(raw), 'sha256': checksum})
    return {'archive_sha256': actual, 'crc_valid': True, 'files': len(entries),
            'manifest_checksums_matched': len(checks),
            'authenticity_note': 'Checksums establish internal consistency, not a publisher signature.',
            'entries': entries}


def probes(report):
    extracted = ROOT / 'work/review-kit' / PREFIX
    for entry in report['entries']:
        if hashlib.sha256((extracted/entry['path']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Extracted reference changed')
    sys.path.insert(0, str(extracted))
    from apex_epoch.database import Store
    from apex_epoch.workqueue import WorkQueue
    from apex_epoch.worker import OfflineWorker
    from apex_epoch.policy import Gateway, ActionRequest
    from apex_epoch.models import Domain, Risk
    from apex_epoch.coverage import SearchCoverage
    result = {}
    store = Store(':memory:')
    try:
        q = WorkQueue(store)
        q.submit('j1', 'offline_report', {}, key='k1', available_at=1)
        Gateway(store).kill('STOP_EXECUTION')
        outcome = OfflineWorker(store).run_one({'offline_report': lambda p: {}}, now=2)
        result['worker_executes_despite_stop'] = outcome['status'] == 'COMPLETE'
        q.submit('j2', 'offline_report', {}, key='k2', available_at=1)
        q.claim('same-worker', now=2, lease_seconds=5)
        q.claim('same-worker', now=7, lease_seconds=5)
        result['old_attempt_can_finish_reclaimed_lease_without_token'] = (
            q.finish('j2', 'same-worker', success=True, now=8) == 'COMPLETE')
        # Separate state/audit transactions: injected audit failure leaves queued state.
        previous = store.event
        def fail(*args, **kwargs): raise RuntimeError('injected audit failure')
        store.event = fail
        try:
            q.submit('j3', 'offline_report', {}, key='k3', available_at=1)
        except RuntimeError:
            pass
        finally:
            store.event = previous
        result['queue_state_commits_without_audit_event'] = (
            store.db.execute("SELECT count(*) FROM tasks WHERE id='j3'").fetchone()[0] == 1
            and store.db.execute("SELECT count(*) FROM events WHERE ref='j3'").fetchone()[0] == 0)
        g = Gateway(store); g.recovery(human_confirmation=True)
        g.capability('offline_report', 'AUTO_ALLOWED')
        result['nonfinite_cost_passes_gateway'] = g.check(ActionRequest(
            't1', 'offline_report', Domain.SYSTEM, 'local', Risk.LOW,
            estimated_cost_minor=float('nan'))).allowed
        c = SearchCoverage('c1', 'question', 'family', 'scope', 1.5, 1.5, 0.5,
                           '2026-11-09T00:00:00Z', 'v1', True)
        result['fractional_counts_accepted_as_full_coverage'] = c.evidence_gaps()['covered_fully']
    finally:
        store.close()
    if not all(result.values()):
        raise AssertionError('Reference defect reproduction changed')
    return {'reproduced': result, 'disposition': 'DO_NOT_IMPORT_REFERENCE_RUNTIME',
            'scope': 'Synthetic in-memory adverse cases; not production incidents'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe-reference', action='store_true')
    args = parser.parse_args()
    report = verify()
    if args.probe_reference:
        report['adversarial_probe'] = probes(report)
    print(json.dumps(report, indent=2))
