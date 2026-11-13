#!/usr/bin/env python3
"""VPS-side: queue a browser task for the laptop agent and read its result. No network, no SSH: it writes to the local journal.
  python3 scripts/laptop_task.py enqueue "Open the OAuth client list" "https://console.cloud.google.com/auth/clients?project=apex-personal" ['[{"action":"click","selector":"text=Next"}]']
  python3 scripts/laptop_task.py status <task-id>        python3 scripts/laptop_task.py summary
  python3 scripts/laptop_task.py demo ["Apex is Alive"]    (opens Notepad on the laptop showing fixed text; no keystrokes, no other program)
The laptop owner approves every task there (y/N); the agent never types secrets or clicks consent buttons and returns only step status, final host and page title.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from apex.bridge_queue import BridgeQueue, QueueError      # noqa: E402
from apex.kernel.memory import Ledger                      # noqa: E402


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 64
    with Ledger(ROOT) as ledger:
        queue = BridgeQueue(ledger)
        try:
            if argv[1] == "enqueue" and len(argv) >= 4:
                print(queue.enqueue(argv[2], argv[3], json.loads(argv[4]) if len(argv) > 4 else []))
            elif argv[1] == "demo":
                print(queue.enqueue_notepad_demo(argv[2] if len(argv) > 2 else "Apex is Alive"))
            elif argv[1] == "status" and len(argv) == 3:
                print(json.dumps(queue.status(argv[2]), indent=1))
            elif argv[1] == "summary":
                print(json.dumps(queue.summary(), indent=1))
            else:
                print(__doc__)
                return 64
        except (QueueError, ValueError) as exc:
            print(f"laptop_task: {exc}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
