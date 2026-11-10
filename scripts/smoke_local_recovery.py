"""Restore a synthetic local SQLite journal; never reads an existing runtime."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'core'))
from apex.kernel.memory import Ledger


def main():
    (ROOT/'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'work', prefix='recovery-drill-') as temp:
        source, restored = Path(temp)/'source', Path(temp)/'restored'
        source.mkdir(); restored.mkdir()
        with Ledger(source) as ledger:
            ledger.append('fixture', 'decision', 'opportunity', {
                'domain': 'opportunity', 'actions_executed': [],
                'synthetic': True, 'status': 'NO_FIELD_EVIDENCE'})
            expected = ledger.records('opportunity')
        stamp = time.monotonic()
        with Ledger.read_only(source) as original, Ledger(restored) as target:
            original.db.backup(target.db)
        with Ledger.read_only(restored) as recovered:
            actual = recovered.records('opportunity')
            count = recovered.verify()
        seconds = time.monotonic() - stamp
        if actual != expected or count != 1:
            raise AssertionError('Restore mismatch')
        raw = (restored/'runtime/kernel.sqlite3').read_bytes()
        print(json.dumps({'status': 'PASS_LOCAL_SYNTHETIC_RESTORE',
                          'events_restored': count, 'reopen_matches_source': actual == expected,
                          'restored_sha256': hashlib.sha256(raw).hexdigest(),
                          'elapsed_seconds': seconds, 'production_restore_tested': False,
                          'encryption_tested': False, 'offsite_backup_tested': False,
                          'scope': 'One isolated stdlib SQLite backup/reopen; not operational MTTR or SLO.'}, indent=2))


if __name__ == '__main__': main()
