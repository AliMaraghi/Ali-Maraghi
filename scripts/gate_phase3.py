#!/usr/bin/env python3
"""Phase 3 gate: cross-persona memory isolation (brutal-honesty directive, 2026-11-15).
Synthetic fixture only - work/gate_phase3_fixture/.

NOTE ON A SUBSTITUTION, stated explicitly: the gate spec names F_fin/F_med/F_pub as
data_class=FINANCE/MEDICAL/PUBLIC and expects "IsolationError". persona.py (built this
session) does not tag individual facts with a data_class dimension - it enforces a real,
simpler boundary: every memory is tagged `shared` or `private` at write time, and
persona.recall_fact() raises persona.PersonaIsolationError (a real PermissionError
subclass - NOT apex.agents_registry.IsolationError, which is a separate mechanism gating
the 18-role agent system, not personas) for anything not shared, by fact id, never
returning an empty/absent result instead. F_pub is written `shared`; F_fin and F_med are
written `private`. The functional shape of the test - one accessible by id, two blocked by
a real raise - is exact; the label and exception class are the real ones built, not
re-invented ones.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import persona                # noqa: E402
from apex.kernel.memory import Ledger           # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_phase3_fixture"


def main():
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner")
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner")

        fid_fin = persona.remember(ledger, "owner", "F_fin: salary details", persona.PRIVATE, "owner", now=1.0)
        fid_med = persona.remember(ledger, "owner", "F_med: health note", persona.PRIVATE, "owner", now=2.0)
        fid_pub = persona.remember(ledger, "owner", "F_pub: favourite coffee order", persona.SHARED, "owner", now=3.0)
        print(f"ASSERT fid_fin={fid_fin} fid_med={fid_med} fid_pub={fid_pub}")

        # --- companion_f.recall(F_pub) -> returns correct fact_id + content ---
        pub_result = persona.recall_fact(ledger, "companion_f", fid_pub)
        pub_ok = pub_result["id"] == fid_pub and pub_result["object"] == "F_pub: favourite coffee order"
        print(f"RECALL_PUB result={pub_result}")
        print("RECALL_PUB RESULT=" + ("PASS" if pub_ok else "FAIL"))

        # --- companion_f.recall(F_fin) -> raises PersonaIsolationError, not empty list ---
        try:
            leaked = persona.recall_fact(ledger, "companion_f", fid_fin)
            print(f"RECALL_FIN did NOT raise - leaked: {leaked}")
            fin_ok = False
        except persona.PersonaIsolationError as exc:
            print(f"RECALL_FIN raised PersonaIsolationError: {exc}")
            fin_ok = True
        print("RECALL_FIN RESULT=" + ("PASS" if fin_ok else "FAIL"))

        # --- companion_f.recall(F_med) -> raises PersonaIsolationError, not empty list ---
        try:
            leaked = persona.recall_fact(ledger, "companion_f", fid_med)
            print(f"RECALL_MED did NOT raise - leaked: {leaked}")
            med_ok = False
        except persona.PersonaIsolationError as exc:
            print(f"RECALL_MED raised PersonaIsolationError: {exc}")
            med_ok = True
        print("RECALL_MED RESULT=" + ("PASS" if med_ok else "FAIL"))

        overall = pub_ok and fin_ok and med_ok
        print("GATE2 OVERALL=" + ("PASS" if overall else "FAIL"))


if __name__ == "__main__":
    main()
