#!/usr/bin/env python3
"""Phase 3 gate: cross-persona memory isolation, GATE B (brutal-honesty directive,
2026-11-15). Synthetic fixture only - work/gate_phase3_fixture/.

FIXED per VERIFICATION GAP 2: the previous version of this script wrote F_fin/F_med as
PRIVATE, so recall_fact() stopped at GATE A (NOT_SHARED) and never exercised GATE B
(data_class/grants) at all - a stale test that looked like it covered the data_class rule
but didn't. F_fin/F_med/F_pub are now all written SHARED with their real data_class, and
companion_f's card carries an explicit (verified) grants=[] - so a shared FINANCE/MEDICAL
fact with no grant now reaches, and fails, DATA_CLASS_DENIED specifically, not NOT_SHARED.

Uses persona.recall_fact()/persona.PersonaIsolationError, the real mechanism built this
session - not core.apex.agents_registry.IsolationError, which is a separate mechanism
gating the 18-role agent system, not personas (same substitution noted in this script's
prior version).
"""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, persona     # noqa: E402
from apex.kernel.memory import Ledger                # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_phase3_fixture"


def main():
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    private_key = secrets.token_bytes(32)          # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)
    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   private_key)
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=[])

        fid_fin = persona.remember(ledger, "owner", "F_fin: salary details", persona.SHARED, "owner",
                                   data_class="FINANCE", private_key_bytes=private_key, now=1.0)
        fid_med = persona.remember(ledger, "owner", "F_med: health note", persona.SHARED, "owner",
                                   data_class="MEDICAL", private_key_bytes=private_key, now=2.0)
        fid_pub = persona.remember(ledger, "owner", "F_pub: favourite coffee order", persona.SHARED, "owner",
                                   data_class="PUBLIC", now=3.0)
        print(f"ASSERT fid_fin={fid_fin} fid_med={fid_med} fid_pub={fid_pub}")

        # --- companion_f.recall(F_pub) -> returns correct fact_id + content, no key needed ---
        pub_result = persona.recall_fact(ledger, "companion_f", fid_pub)
        pub_ok = pub_result["id"] == fid_pub and pub_result["object"] == "F_pub: favourite coffee order"
        print(f"RECALL_PUB result={pub_result}")
        print("RECALL_PUB RESULT=" + ("PASS" if pub_ok else "FAIL"))

        # --- companion_f.recall(F_fin), shared=True, grants=[] -> DATA_CLASS_DENIED ---
        try:
            leaked = persona.recall_fact(ledger, "companion_f", fid_fin, public_key)
            print(f"RECALL_FIN did NOT raise - leaked: {leaked}")
            fin_ok = False
        except persona.PersonaIsolationError as exc:
            print(f"RECALL_FIN raised PersonaIsolationError: {exc}")
            fin_ok = "DATA_CLASS_DENIED" in str(exc)
        print("RECALL_FIN RESULT=" + ("PASS" if fin_ok else "FAIL"))

        # --- companion_f.recall(F_med), shared=True, grants=[] -> DATA_CLASS_DENIED ---
        try:
            leaked = persona.recall_fact(ledger, "companion_f", fid_med, public_key)
            print(f"RECALL_MED did NOT raise - leaked: {leaked}")
            med_ok = False
        except persona.PersonaIsolationError as exc:
            print(f"RECALL_MED raised PersonaIsolationError: {exc}")
            med_ok = "DATA_CLASS_DENIED" in str(exc)
        print("RECALL_MED RESULT=" + ("PASS" if med_ok else "FAIL"))

        overall = pub_ok and fin_ok and med_ok
        print("GATE2 OVERALL=" + ("PASS" if overall else "FAIL"))


if __name__ == "__main__":
    main()
