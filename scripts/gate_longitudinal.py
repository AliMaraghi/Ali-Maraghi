#!/usr/bin/env python3
"""MEDIUM 1 (brutal-honesty directive, 2026-11-15): longitudinal state - 1000 signed facts,
50 persona card versions (alternating grant/revoke), real wall-clock timing. Synthetic
fixture only - work/gate_longitudinal_fixture/.
"""
import secrets
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, facts, persona     # noqa: E402
from apex.kernel.memory import Ledger                        # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_longitudinal_fixture"


def build_fixture(n_facts, private_key):
    if GATE_ROOT.exists():
        shutil.rmtree(GATE_ROOT)
    GATE_ROOT.mkdir(parents=True)
    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner", private_key)
        for i in range(n_facts):
            facts.assert_signed_fact(ledger, "owner", f"p{i}", f"fact number {i}", "owner",
                                     "PUBLIC", private_key, now=float(i))


def main():
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)

    print("=== Required gate: 1000 facts + 50 card versions ===")
    build_fixture(1000, private_key)
    with Ledger(GATE_ROOT) as ledger:
        for i in range(50):
            grants = ["FINANCE"] if i % 2 == 0 else []     # alternating grant/revoke
            persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                       "I am a synthetic companion persona, not a real person.", "owner",
                                       private_key, grants=grants, now=1000.0 + i)
    with Ledger.read_only(GATE_ROOT) as ledger:
        t0 = time.perf_counter()
        chain_result = facts.verify_fact_chain(ledger, public_key)
        chain_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        card_verifies = persona.verify_persona_card(ledger, "companion_f", public_key)
        card_ms = (time.perf_counter() - t1) * 1000

        final_card = persona.read_persona_card(ledger, "companion_f")

    total_ms = chain_ms + card_ms
    print(f"verify_fact_chain(1000 signed facts): ok={chain_result['ok']} length={chain_result['length']} "
          f"time_ms={chain_ms:.2f}")
    print(f"verify_persona_card(current, version={final_card['version']}, grants={final_card['grants']}): "
          f"ok={card_verifies} time_ms={card_ms:.2f}")
    print(f"total_time_ms={total_ms:.2f}")
    pass_required = chain_result["ok"] and card_verifies and total_ms < 2000
    print("REQUIRED_GATE RESULT=" + ("PASS" if pass_required else "FAIL"))

    print("\n=== Scaling curve (disclosure only, per instruction - not a fix) ===")
    curve = []
    for n in (100, 500, 1000, 5000):
        build_fixture(n, private_key)
        with Ledger.read_only(GATE_ROOT) as ledger:
            t0 = time.perf_counter()
            result = facts.verify_fact_chain(ledger, public_key)
            elapsed_ms = (time.perf_counter() - t0) * 1000
        curve.append((n, elapsed_ms))
        print(f"n={n:5d}  verify_fact_chain_ms={elapsed_ms:9.2f}  ok={result['ok']}")

    # Report the growth ratio between successive points - a roughly constant ratio close to
    # the input-size ratio indicates linear (O(n)); a ratio that grows faster than the input
    # ratio indicates superlinear behaviour. Disclosed, not fixed, per the instruction.
    print("\nGrowth ratios (time_ratio / size_ratio - near 1.0 is linear, growing is superlinear):")
    for (n0, t0), (n1, t1) in zip(curve, curve[1:]):
        size_ratio = n1 / n0
        time_ratio = (t1 / t0) if t0 > 0 else float("inf")
        print(f"  {n0}->{n1}: size_ratio={size_ratio:.2f} time_ratio={time_ratio:.2f} "
              f"normalized={time_ratio / size_ratio:.2f}")


if __name__ == "__main__":
    main()
