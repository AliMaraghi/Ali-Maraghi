"""The GOVERNING 18-role federation (A-1 .. A-18, 11 Nov 2026 founder edition) as specifications.

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


_PUBLIC = frozenset({legacy.PUBLIC})
_ROLES = (
    ("Strategic Intelligence", "Monitor macro trends and build scenarios", "opportunity", _PUBLIC, IMPLEMENTED_LOCAL),
    ("Scientific Research", "Search scientific papers and separate evidence", "opportunity", _PUBLIC, IMPLEMENTED_LOCAL),
    ("Evidence & Verification", "Find contradictions and audit data", "opportunity", _PUBLIC, SPEC_ONLY),
    ("Personal Context", "Manage the personal dossier and causal goals", "personal", _PUBLIC, SPEC_ONLY),
    ("Career & Industry", "Analyse the job market and opportunities (NVIDIA, Amazon, AMD)", "opportunity", _PUBLIC, IMPLEMENTED_LOCAL),
    ("Operations & Executive", "Analyse e-mail and manage administrative projects", "personal", _PUBLIC, SPEC_ONLY),
    ("Wealth Discovery", "Find economic and investment opportunities", "opportunity", _PUBLIC, SPEC_ONLY),
    ("Financial Intelligence", "Tax, ESPP, UC and housing analysis", "personal", frozenset({legacy.PUBLIC, legacy.FINANCE}), IMPLEMENTED_LOCAL),
    ("Legal & Compliance", "Review UK rules (FCA, HMRC, ICO)", "opportunity", _PUBLIC, SPEC_ONLY),
    ("Social & Relational", "Analyse and suggest authentic social interactions", "personal", _PUBLIC, SPEC_ONLY),
    ("Creative Direction", "Develop artistic ideas and visual identity", "studio", _PUBLIC, SPEC_ONLY),
    ("Screenwriting & Film", "Screenplay, storyboard and direction", "studio", _PUBLIC, SPEC_ONLY),
    ("Publishing & Audience", "Publication calendar and audience feedback", "studio", _PUBLIC, SPEC_ONLY),
    ("Security & Privacy", "Threat modelling and data isolation", "personal", _PUBLIC, SPEC_ONLY),
    ("Health & Longevity", "Parse owner-exported lab results into provenance-tagged rows (research aid only)",
     "personal", frozenset({legacy.PUBLIC, legacy.MEDICAL}), IMPLEMENTED_LOCAL),
    ("Behavioral Ergonomics", "Fit the daily plan to the energy level", "personal", _PUBLIC, SPEC_ONLY),
    ("Adversarial Evaluation", "Simulate failure and critique strategies (red team)", "opportunity", _PUBLIC, SPEC_ONLY),
    ("Self-Evolution & Systems", "Controlled code upgrades in a sandbox", "opportunity", _PUBLIC, SPEC_ONLY),
)
ROLES = tuple(RoleSpec(f"A-{n}", name, mission, domain, allowed, status, "8-12" if n == 3 else None)
              for n, (name, mission, domain, allowed, status) in enumerate(_ROLES, 1))
BY_ID = {r.agent_id: r for r in ROLES}
assert len(ROLES) == 18


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
