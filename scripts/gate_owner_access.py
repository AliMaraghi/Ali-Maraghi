#!/usr/bin/env python3
"""MEDIUM 2 (brutal-honesty directive, 2026-11-15): the owner-twin access rule, made
explicit and named. Synthetic fixture only - work/gate_owner_access_fixture/."""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, persona     # noqa: E402
from apex.kernel.memory import Ledger                # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_owner_access_fixture"


def main():
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    import shutil
    if (GATE_ROOT / "runtime").exists():
        shutil.rmtree(GATE_ROOT)
        GATE_ROOT.mkdir(parents=True)
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)

    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner_twin", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner", private_key)
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=[])            # NO grant
        persona.write_persona_card(ledger, "third_party", "Zed", "neutral", False,
                                   "A third synthetic persona, for the grant-path demonstration.", "owner",
                                   private_key, grants=["FINANCE"])   # explicit grant

        fid_fin = persona.remember(ledger, "owner_twin", "owner's salary details", persona.SHARED, "owner",
                                   data_class="FINANCE", private_key_bytes=private_key, now=1.0)
        print(f"ASSERT fid_fin={fid_fin}")

        # A. owner_twin.recall_fact(owner's own F_fin) with grants=[] -> RETURN
        result_a = persona.recall_fact(ledger, "owner_twin", fid_fin)   # no public_key_bytes even supplied
        print(f"A owner_twin.recall_fact(own F_fin) -> {result_a}")
        pass_a = result_a["id"] == fid_fin
        print("A RESULT=" + ("PASS" if pass_a else "FAIL") +
              "  DECISION=RETURN (self-access is never gated - see the named code path below)")

        # B. companion_f.recall_fact(owner's F_fin) with grants=[] -> DATA_CLASS_DENIED
        try:
            leaked = persona.recall_fact(ledger, "companion_f", fid_fin, public_key)
            print(f"B companion_f.recall_fact(owner's F_fin) did NOT raise - leaked: {leaked}")
            pass_b = False
        except persona.PersonaIsolationError as exc:
            print(f"B companion_f.recall_fact(owner's F_fin) raised: {exc}")
            pass_b = "DATA_CLASS_DENIED" in str(exc)
        print("B RESULT=" + ("PASS" if pass_b else "FAIL"))

        # C. The code path that grants owner_twin implicit access, named exactly.
        print("C CODE_PATH=core/apex/kernel/persona.py:recall_fact(), the line "
              "'if owning_persona_id == reading_persona_id: return fact' - a persona reading "
              "a fact whose subject is its OWN persona:<id> returns immediately, before GATE A "
              "(shared) or GATE B (data_class/grants) are even evaluated. This is not 'the "
              "owner is special' as a persona_id string check - it is 'you can always read "
              "what you yourself hold', which is true for every persona equally, including "
              "companion_f reading companion_f's own facts.")

        # D. The explicit-grant path for a THIRD, non-owner, non-self persona - proving the
        # grant mechanism (not self-access) is what makes cross-persona reads work when they
        # do, independent of who happens to be "the owner".
        try:
            result_d = persona.recall_fact(ledger, "third_party", fid_fin, public_key)
            print(f"D third_party (grants=['FINANCE']).recall_fact(owner's F_fin) -> {result_d}")
            pass_d = result_d["id"] == fid_fin
        except persona.PersonaIsolationError as exc:
            print(f"D third_party.recall_fact(owner's F_fin) raised unexpectedly: {exc}")
            pass_d = False
        print("D RESULT=" + ("PASS" if pass_d else "FAIL"))

        print("MEDIUM2 OVERALL=" + ("PASS" if (pass_a and pass_b and pass_d) else "FAIL"))


if __name__ == "__main__":
    main()
