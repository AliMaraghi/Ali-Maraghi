"""Usage from running Apex core container:

python -m apex.discovery.cli --from-db

Or on a local Python 3.10+ machine, no dependencies:

PYTHONPATH=core python -m apex.discovery.cli --fixture
"""
import argparse
import json
import sys
from .engine import Signal, run_cycle, blocked

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
            from pathlib import Path
            p=Path(args.input_json)
            if p.stat().st_size > 65536: raise ValueError('Input JSON over 64 KiB')
            doc=json.loads(p.read_text(encoding='utf-8'))
            if not isinstance(doc,dict): raise ValueError('Input JSON must be object')
            sig=Signal(**{k:v for k,v in doc.items() if k in {'title','url','source','observed_at','synthetic'}})
        result=run_cycle(sig)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['status']=='BLOCKED_PENDING_EVIDENCE' else 2
    except Exception as exc:
        # Deliberately do not print source content, DB URL or secrets.
        print(json.dumps(blocked('BLOCKED_INPUT_OR_DATABASE_ERROR',source=type(exc).__name__),indent=2))
        return 2

if __name__=='__main__':
    sys.exit(main())
