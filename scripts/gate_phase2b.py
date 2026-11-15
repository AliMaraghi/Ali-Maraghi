#!/usr/bin/env python3
"""GAP 1 (brutal-honesty directive, 2026-11-15): data_class enforcement, proven against the
exact 4-case matrix. Synthetic fixture only - work/gate_phase2b_fixture/."""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, persona     # noqa: E402
from apex.kernel.memory import Ledger               # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_phase2b_fixture"


def main():
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    private_key = secrets.token_bytes(32)          # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)
    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   private_key)

        fid_fin = persona.remember(ledger, "owner", "F_fin content", persona.SHARED, "owner",
                                   data_class="FINANCE", private_key_bytes=private_key, now=1.0)
        fid_med = persona.remember(ledger, "owner", "F_med content", persona.SHARED, "owner",
                                   data_class="MEDICAL", private_key_bytes=private_key, now=2.0)
        fid_pub = persona.remember(ledger, "owner", "F_pub content", persona.SHARED, "owner",
                                   data_class="PUBLIC", now=3.0)
        print(f"ASSERT fid_fin={fid_fin} fid_med={fid_med} fid_pub={fid_pub}")

        results = []

        # Case 1: F_fin, shared=TRUE, female grants=[] -> RAISES
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=[], now=10.0)
        try:
            persona.recall_fact(ledger, "companion_f", fid_fin, public_key)
            case1 = "DID_NOT_RAISE"
        except persona.PersonaIsolationError as exc:
            case1 = f"RAISED:{exc}"
        print(f"CASE1 F_fin grants=[] -> {case1}")
        case1_pass = case1.startswith("RAISED")
        print("CASE1 RESULT=" + ("PASS" if case1_pass else "FAIL"))
        results.append(case1_pass)

        # Case 2: F_fin, shared=TRUE, female grants=['FINANCE'] -> RETURNS
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=["FINANCE"], now=11.0)
        try:
            result2 = persona.recall_fact(ledger, "companion_f", fid_fin, public_key)
            case2 = f"RETURNED:{result2['object']}"
            case2_pass = result2["id"] == fid_fin
        except persona.PersonaIsolationError as exc:
            case2 = f"RAISED:{exc}"
            case2_pass = False
        print(f"CASE2 F_fin grants=['FINANCE'] -> {case2}")
        print("CASE2 RESULT=" + ("PASS" if case2_pass else "FAIL"))
        results.append(case2_pass)

        # Case 3: F_med, shared=TRUE, female grants=['FINANCE'] -> RAISES (FINANCE grant does not cover MEDICAL)
        try:
            persona.recall_fact(ledger, "companion_f", fid_med, public_key)
            case3 = "DID_NOT_RAISE"
        except persona.PersonaIsolationError as exc:
            case3 = f"RAISED:{exc}"
        print(f"CASE3 F_med grants=['FINANCE'] -> {case3}")
        case3_pass = case3.startswith("RAISED")
        print("CASE3 RESULT=" + ("PASS" if case3_pass else "FAIL"))
        results.append(case3_pass)

        # Case 4: F_pub, shared=TRUE, female grants=[] -> RETURNS (PUBLIC needs no grant)
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=[], now=12.0)
        try:
            result4 = persona.recall_fact(ledger, "companion_f", fid_pub, public_key)
            case4 = f"RETURNED:{result4['object']}"
            case4_pass = result4["id"] == fid_pub
        except persona.PersonaIsolationError as exc:
            case4 = f"RAISED:{exc}"
            case4_pass = False
        print(f"CASE4 F_pub grants=[] -> {case4}")
        print("CASE4 RESULT=" + ("PASS" if case4_pass else "FAIL"))
        results.append(case4_pass)

        print("GAP1 OVERALL=" + ("PASS" if all(results) else "FAIL"))


if __name__ == "__main__":
    main()
