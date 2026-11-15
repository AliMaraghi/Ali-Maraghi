#!/usr/bin/env python3
"""THE HOLE (brutal-honesty directive, 2026-11-15): persona.grants used to live in an
UNSIGNED JSON blob - anyone with DB write access could add 'MEDICAL' to a persona's grants
without touching any fact's owner_sig, bypassing DATA_CLASS_DENIED entirely. This proves the
fix: cards are now signed, grants included in the signed payload, with a version/
prev_card_sig chain. Synthetic fixture only - work/gate_grants_sig_fixture/.
"""
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, persona     # noqa: E402
from apex.kernel.memory import Ledger                # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_grants_sig_fixture"


def main():
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    private_key = secrets.token_bytes(32)          # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)

    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   private_key)
        v1_fact_id = persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                                "I am a synthetic companion persona, not a real person.", "owner",
                                                private_key, grants=[])
        v1_card = persona.read_persona_card(ledger, "companion_f")
        fid_fin = persona.remember(ledger, "owner", "F_fin content", persona.SHARED, "owner",
                                   data_class="FINANCE", private_key_bytes=private_key, now=1.0)
        print(f"SETUP v1_fact_id={v1_fact_id} v1_card={v1_card} fid_fin={fid_fin}")

    # --- Attack: tamper grants directly in the DB, WITHOUT re-signing ---
    db_path = GATE_ROOT / "runtime" / "kernel.sqlite3"
    raw = sqlite3.connect(str(db_path))
    import json
    tampered_card = dict(v1_card)
    tampered_card["grants"] = ["FINANCE"]           # the attack: add a grant, keep the old owner_sig
    raw.execute("UPDATE facts SET object=? WHERE id=?", (json.dumps(tampered_card), v1_fact_id))
    raw.commit()
    raw.close()
    print(f"ATTACK tampered v1's grants to ['FINANCE'] in place, owner_sig left unchanged (not re-signed)")

    with Ledger(GATE_ROOT) as ledger:
        card_verifies = persona.verify_persona_card(ledger, "companion_f", public_key)
        print(f"VERIFY_AFTER_TAMPER verify_persona_card={card_verifies}")
        try:
            leaked = persona.recall_fact(ledger, "companion_f", fid_fin, public_key)
            print(f"RECALL_AFTER_TAMPER did NOT raise - leaked: {leaked}")
            tamper_blocked = False
        except persona.PersonaIsolationError as exc:
            print(f"RECALL_AFTER_TAMPER raised PersonaIsolationError: {exc}")
            tamper_blocked = "PERSONA_CARD_UNVERIFIED" in str(exc)
        print("TAMPER_TEST RESULT=" + ("PASS" if (not card_verifies and tamper_blocked) else "FAIL"))

        # --- Legitimate re-sign: a NEW version with the real grant, properly chained ---
        v2_fact_id = persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                                "I am a synthetic companion persona, not a real person.", "owner",
                                                private_key, grants=["FINANCE"])
        v2_card = persona.read_persona_card(ledger, "companion_f")
        print(f"RESIGN v2_fact_id={v2_fact_id} v2_card={v2_card}")
        v2_verifies = persona.verify_persona_card(ledger, "companion_f", public_key)
        print(f"VERIFY_AFTER_RESIGN verify_persona_card={v2_verifies}")
        try:
            result = persona.recall_fact(ledger, "companion_f", fid_fin, public_key)
            print(f"RECALL_AFTER_RESIGN returned: {result}")
            resign_ok = result["id"] == fid_fin
        except persona.PersonaIsolationError as exc:
            print(f"RECALL_AFTER_RESIGN raised unexpectedly: {exc}")
            resign_ok = False
        print("RESIGN_TEST RESULT=" + ("PASS" if (v2_verifies and resign_ok) else "FAIL"))

        # --- Old version is never consulted: a CLEAN lineage (no tampering involved here),
        # so v1's real original grants are genuinely preserved in history and genuinely
        # different from v2's - proving recall_fact() always resolves to the current card. ---
        persona.write_persona_card(ledger, "companion_clean", "Nova2", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=[])                                  # v1, real, untampered
        fid_fin2 = persona.remember(ledger, "owner", "F_fin content 2", persona.SHARED, "owner",
                                    data_class="FINANCE", private_key_bytes=private_key, now=2.0)
        try:
            persona.recall_fact(ledger, "companion_clean", fid_fin2, public_key)
            v1_leaked = True
        except persona.PersonaIsolationError:
            v1_leaked = False
        persona.write_persona_card(ledger, "companion_clean", "Nova2", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=["FINANCE"])                          # v2, real, untampered
        history2 = persona.persona_card_history(ledger, "companion_clean")
        v1_real = next(h["card"] for h in history2 if h["card"]["version"] == 1)
        v2_real = next(h["card"] for h in history2 if h["card"]["version"] == 2)
        print(f"HISTORY v1_grants={v1_real['grants']} v2_grants={v2_real['grants']} "
              f"(both real, neither tampered)")
        try:
            result2 = persona.recall_fact(ledger, "companion_clean", fid_fin2, public_key)
            v2_works = result2["id"] == fid_fin2
        except persona.PersonaIsolationError:
            v2_works = False
        # The actual claim: with v1 CURRENT (before v2 existed), access was denied
        # (v1_leaked is False); with v2 CURRENT (after superseding v1), access works
        # (v2_works is True) - recall_fact() has no parameter to select an old version at
        # all, so "recall via v1" after v2 exists is structurally impossible, not merely
        # untested.
        old_version_not_used = (v1_leaked is False) and (v2_works is True) and v1_real["grants"] != v2_real["grants"]
        print(f"OLD_VERSION_TEST v1_denied_when_current={not v1_leaked} v2_allowed_when_current={v2_works}")
        print("OLD_VERSION_TEST RESULT=" + ("PASS" if old_version_not_used else "FAIL"))

        overall = (not card_verifies) and tamper_blocked and v2_verifies and resign_ok and old_version_not_used
        print("HOLE OVERALL=" + ("PASS" if overall else "FAIL"))


if __name__ == "__main__":
    main()
