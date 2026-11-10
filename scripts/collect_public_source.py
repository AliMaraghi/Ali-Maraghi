"""Explicit one-page public research command. No service or background polling."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'core'))
from apex.sources.contracts_finder import collect, SourceError
from apex.kernel.policy import KillState
from apex.kernel.memory import Ledger
from apex.kernel.jobs import Jobs
from apex.kernel.policy import enforce_durable_stop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-public', action='store_true')
    parser.add_argument('--from-date', required=True)
    parser.add_argument('--to-date', required=True)
    parser.add_argument('--kill-state', choices=[s.value for s in KillState], default='RUNNING')
    args = parser.parse_args()
    try:
        with Ledger(ROOT) as ledger:
            Jobs(ledger)
            with ledger.transaction():
                enforce_durable_stop(ledger)
                packet = collect(args.from_date, args.to_date, network_authorized=args.fetch_public,
                                 kill_state=KillState(args.kill_state))
        print(json.dumps(packet, indent=2, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_PUBLIC_SOURCE', 'error_type': type(error).__name__,
                          'reason': str(error)[:200] if isinstance(error, SourceError) else 'No usable packet; no retry performed',
                          'usable_packets': 0, 'paid_api_spend_pence': 0}))
        return 2


if __name__ == '__main__': sys.exit(main())
