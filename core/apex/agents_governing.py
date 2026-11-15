"""The GOVERNING role federation (originally A-1 .. A-18, 11 Nov 2026 founder edition; A-12
and A-13 removed 2026-11-15, see below) as specifications.

Source: docs/apex_handoff_20261111/APEX_4_4_MANIFESTO_20261111_FOUNDER_UPLOAD.md section 8 (lines 69-86). The older 8-x slot set (agents_registry.py) is preserved separately; slot 8-12 maps to A-3.
Nothing here is invented policy: the manifesto does not give per-role data tiers for this roster, so every role defaults to PUBLIC data only and a role is granted more only where the role itself
cannot work without it (A-8 receives owner-entered FINANCE inputs). Roles with no runtime are SPEC_ONLY and are never run.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import agents_registry as legacy

IMPLEMENTED_LOCAL, SPEC_ONLY = "IMPLEMENTED_LOCAL", "SPEC_ONLY"


@dataclass(frozen=True)
class RoleSpec:
    agent_id: str
    name: str
    mission: str
    domain: str
    allowed_data: frozenset
    status: str = SPEC_ONLY
    legacy_slot: str | None = None


# A-12 (Screenwriting & Film) and A-13 (Publishing & Audience) REMOVED 2026-11-15 per
# mission directive ("add breadth with no depth") - not commented out, not SPEC_ONLY-marked,
# removed from the tuple entirely. Every remaining id below is given EXPLICITLY (not via
# enumerate) so A-14..A-18 keep their original numbers rather than shifting down to fill the
# gap - code and tests elsewhere (agents_impl.py, test_agents_runtime.py) hardcode A-1, A-2,
# A-3, A-5, A-8, A-10, A-15 and must not have those meanings change under them.
_PUBLIC = frozenset({legacy.PUBLIC})
_ROLES = (
    ("A-1", "Strategic Intelligence", "Monitor macro trends and build scenarios", "opportunity", _PUBLIC, IMPLEMENTED_LOCAL, None),
    ("A-2", "Scientific Research", "Search scientific papers and separate evidence", "opportunity", _PUBLIC, IMPLEMENTED_LOCAL, None),
    ("A-3", "Evidence & Verification", "Scan the fact store for genuine contradictions (resolves nothing, picks no value as correct)",
     "opportunity", _PUBLIC, IMPLEMENTED_LOCAL, "8-12"),
    ("A-4", "Personal Context", "Manage the personal dossier and causal goals", "personal", _PUBLIC, SPEC_ONLY, None),
    ("A-5", "Career & Industry", "Analyse the job market and opportunities (NVIDIA, Amazon, AMD)", "opportunity", _PUBLIC, IMPLEMENTED_LOCAL, None),
    ("A-6", "Operations & Executive", "Analyse e-mail and manage administrative projects", "personal", _PUBLIC, SPEC_ONLY, None),
    ("A-7", "Wealth Discovery", "Find economic and investment opportunities", "opportunity", _PUBLIC, SPEC_ONLY, None),
    ("A-8", "Financial Intelligence", "Tax, ESPP, UC and housing analysis", "personal", frozenset({legacy.PUBLIC, legacy.FINANCE}), IMPLEMENTED_LOCAL, None),
    ("A-9", "Legal & Compliance", "Review UK rules (FCA, HMRC, ICO)", "opportunity", _PUBLIC, SPEC_ONLY, None),
    ("A-10", "Social & Relational", "Prepare owner-reviewed relationship notes/drafts/bio checklists (advisory text only, never sent)",
     "personal", _PUBLIC, IMPLEMENTED_LOCAL, None),
    ("A-11", "Creative Direction", "Develop artistic ideas and visual identity", "studio", _PUBLIC, SPEC_ONLY, None),
    ("A-14", "Security & Privacy", "Threat modelling and data isolation", "personal", _PUBLIC, SPEC_ONLY, None),
    ("A-15", "Health & Longevity", "Parse owner-exported lab results into provenance-tagged rows (research aid only)",
     "personal", frozenset({legacy.PUBLIC, legacy.MEDICAL}), IMPLEMENTED_LOCAL, None),
    ("A-16", "Behavioral Ergonomics", "Fit the daily plan to the energy level", "personal", _PUBLIC, SPEC_ONLY, None),
    ("A-17", "Adversarial Evaluation", "Simulate failure and critique strategies (red team)", "opportunity", _PUBLIC, SPEC_ONLY, None),
    ("A-18", "Self-Evolution & Systems", "Controlled code upgrades in a sandbox", "opportunity", _PUBLIC, SPEC_ONLY, None),
)
ROLES = tuple(RoleSpec(agent_id, name, mission, domain, allowed, status, legacy_slot)
              for agent_id, name, mission, domain, allowed, status, legacy_slot in _ROLES)
BY_ID = {r.agent_id: r for r in ROLES}
assert len(ROLES) == 16, "18 minus A-12 (Screenwriting) and A-13 (Publishing), removed 2026-11-15"

# FROZEN (mission 2026-11-15, docs/ACTIVE_SYSTEM.md / docs/FROZEN_SYSTEMS.md): A-10 is the
# sole active system during the 21-day measurement window. Freezing is NOT a status change
# (no RoleSpec.status here is touched - "do not flip any role") and not deletion: the code
# stays, scripts/agents_runner.py --once simply skips a frozen name unless --include-frozen
# names it explicitly. Keyed by the system name agents_runner.py's AGENT_FACTORIES uses, not
# by agent_id, because two of the four named systems (mutual_match_platform, marketing_funnel,
# webxr_twin) are not agents_runner.py roles at all - see docs/FROZEN_SYSTEMS.md for why.
FROZEN = {
    # Superseded 2026-11-15, same day: the prior FROZEN set here was
    # {financial_intelligence, mutual_match_platform, marketing_funnel, webxr_twin}.
    # A later mission this same session named a different exact 4 - digital_twin (renamed
    # from webxr_twin), marketing_funnel, mutual_match_platform, adult_social_assist - and
    # did not name financial_intelligence, so financial_intelligence is UNFROZEN below. This
    # replaces, not adds to, the earlier set - see docs/FROZEN_SYSTEMS.md for the correction.
    "digital_twin": "High-risk identity mimicry (face/voice); replaced by a lower-risk "
                     "textual behavioral signature (core/apex/kernel/behavioral_signature.py) "
                     "- frozen, will not be unfrozen.",
    "marketing_funnel": "Static content only (docs/marketing_funnel_apex.md), never a "
                         "runtime agent - frozen here means marked inactive in docs, not "
                         "disabled code.",
    "mutual_match_platform": "Never registered as a runtime agent in agents_runner.py (a "
                              "separate standalone prototype module, mutual_match_platform/) "
                              "- frozen here means marked inactive in docs, not disabled code.",
    "adult_social_assist": "Never registered as a runtime agent in agents_runner.py (a "
                            "separate module, core/apex/adult_social_assist.py) - frozen here "
                            "means marked inactive in docs, not disabled code.",
}


def select_active(names, include_frozen=()):
    """Partition `names` into (active, skipped) against FROZEN. `include_frozen` names are
    treated as active anyway (the explicit override), proving freeze is reversible per-call,
    not a deletion. Pure function - no I/O, no ledger, no agent construction - so it is
    testable without the protected approvals file or a real ledger."""
    include_frozen = set(include_frozen)
    active, skipped = [], {}
    for name in names:
        if name in FROZEN and name not in include_frozen:
            skipped[name] = FROZEN[name]
        else:
            active.append(name)
    return active, skipped


def get(agent_id):
    spec = BY_ID.get(agent_id)
    if spec is None:
        raise KeyError("Unknown agent")
    return spec


def check_inputs(agent_id, data_classes, data_source="personal"):
    spec = get(agent_id)
    if data_source == "corporate":
        raise legacy.IsolationError("CORPORATE_SOURCE_DENIED")
    denied = frozenset(data_classes) - spec.allowed_data
    if denied:
        raise legacy.IsolationError("DATA_CLASS_DENIED:" + ",".join(sorted(denied)))
    return True
