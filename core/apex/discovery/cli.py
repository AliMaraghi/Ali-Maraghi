"""Usage from running Apex core container:

python -m apex.discovery.cli --from-db

Or on a local Python 3.10+ machine, no dependencies:

PYTHONPATH=core python -m apex.discovery.cli --fixture
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from .engine import Signal, run_cycle, blocked

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
MAX_INPUT_BYTES = 65536


def read_offline_input(path):
    """Read a bounded regular JSON file beneath this development workspace.

    Walk directory descriptors without following symlinks, so a renamed path
    cannot redirect a later read outside the workspace. Never read FIFOs/devices.
    """
    relative = Path(path).absolute().relative_to(WORKSPACE_ROOT)
    if not relative.parts or '..' in relative.parts:
        raise ValueError('Input must be a file within the development workspace')
    directory = os.open(WORKSPACE_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            next_directory = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            os.close(directory)
            directory = next_directory
        fd = os.open(
            relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        with os.fdopen(fd, 'rb') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError('Input must be a regular file')
            raw = source.read(MAX_INPUT_BYTES + 1)
    finally:
        os.close(directory)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('Input JSON over 64 KiB')
    doc = json.loads(raw.decode('utf-8'))
    if not isinstance(doc, dict):
        raise ValueError('Input JSON must be object')
    if set(doc) - {'title', 'url', 'source', 'observed_at', 'synthetic'}:
        raise ValueError('Unknown signal fields')
    if any(not isinstance(doc.get(key), str) for key in ('title', 'url')):
        raise ValueError('Signal title and URL must be strings')
    if 'source' in doc and not isinstance(doc['source'], str):
        raise ValueError('Signal source must be a string')
    if doc.get('observed_at') is not None and not isinstance(doc['observed_at'], str):
        raise ValueError('Observation time must be a string or null')
    if 'synthetic' in doc and not isinstance(doc['synthetic'], bool):
        raise ValueError('Synthetic flag must be a boolean')
    return Signal(**doc)

def latest_signal_from_db():
    # This is the only database operation. It reads existing observations;
    # it NEVER writes records, creates tables, or changes running services.
    from apex.storage import list_items
    records = list_items(limit=1)
    if not records: return None
    row = records[0]
    return Signal(
        title=row['title'], url=row['url'], source=row['source'],
        observed_at=row['observed_at'].isoformat(), synthetic=False,
    )

def main(argv=None):
    parser = argparse.ArgumentParser(description='Apex RDE: no-key read-only research experiment')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--from-db',action='store_true',help='Read newest saved public arXiv RSS observation')
    group.add_argument('--fixture',action='store_true',help='Run a clearly marked synthetic example')
    group.add_argument('--input-json',help='Path to user-provided offline signal JSON')
    args=parser.parse_args(argv)
    try:
        if args.fixture:
            sig=Signal(title='[SYNTHETIC EXAMPLE] A research result with unknown market demand',url='https://arxiv.org/abs/0000.00000',source='test-fixture',synthetic=True)
        elif args.from_db:
            sig=latest_signal_from_db()
            if sig is None:
                result=blocked('BLOCKED_NO_PUBLIC_OBSERVATIONS')
                print(json.dumps(result,indent=2,ensure_ascii=False))
                return 2
        else:
            sig=read_offline_input(args.input_json)
        result=run_cycle(sig)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['status']=='BLOCKED_PENDING_EVIDENCE' else 2
    except Exception as exc:
        # Deliberately do not print source content, DB URL or secrets.
        print(json.dumps(blocked('BLOCKED_INPUT_OR_DATABASE_ERROR',source=type(exc).__name__),indent=2))
        return 2

if __name__=='__main__':
    sys.exit(main())
