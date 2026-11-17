#!/usr/bin/env python3
"""Container entry point for the backend (used by docker-compose.local.yml only).

1. If a hosted-API key was mounted as a Docker secret, copy it to /etc/apex with mode 0600
   (voice_api.py refuses a group/world-readable key, which is what a Windows bind mount gives).
2. In local-model mode (APEX_LLM_PROVIDER=ollama) price every LLM SKU at zero: local inference
   has no per-call cost, so the budget ledger still records each call but never denies one.
3. Serve the same WSGI app as production on 0.0.0.0 inside the container; compose publishes it
   to the host's loopback only.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "core"), str(ROOT / "scripts")]

LOCAL_SKUS = ("voice-chat-call", "finance-strategy-step", "twitter-draft-step", "dating-draft-step",
              "academic-personalize-step", "intent-router-step", "intent-planner-step",
              "capability-draft-step", "agent-loop-step", "research-pipeline-step")


def price_local_skus(ledger) -> None:
    from apex.kernel.budget import Budget
    budget = Budget(ledger)
    for sku in LOCAL_SKUS:      # "anthropic" is only the reservation label the existing callers use
        budget.set_price("anthropic", sku, 0, time.time() - 1, "local Ollama inference: no per-call cost")


def main() -> None:
    if "--price-only" in sys.argv:          # used by install_apex.sh on a non-Docker host
        from apex import local_llm
        from apex.kernel.memory import Ledger
        if not local_llm.enabled():
            sys.exit("Refusing: APEX_LLM_PROVIDER is not 'ollama' (zero prices are for local inference only).")
        with Ledger(ROOT) as ledger:
            price_local_skus(ledger)
        print("Local-model SKUs priced at zero.")
        return
    secret, target = Path("/run/secrets/anthropic_key"), Path("/etc/apex/anthropic-key")
    if secret.is_file() and secret.stat().st_size > 0:
        shutil.copyfile(secret, target)
        os.chmod(target, 0o600)
    import voice_api
    from apex import local_llm
    from waitress import serve
    app = voice_api.VoiceChatApp(ROOT)
    if local_llm.enabled():
        price_local_skus(app.ledger)
    serve(app, listen="0.0.0.0:8000", threads=4, connection_limit=32)


if __name__ == "__main__":
    main()
