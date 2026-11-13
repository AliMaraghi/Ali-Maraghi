"""Legacy "8-x" task-role registry (an older, creative/operational task vocabulary), separate
from the modern A-1..A-18 governing roster in agents_governing.py - see that module's docstring:
slot 8-12 maps to modern A-3. A-8 Financial Intelligence is NOT the same entity as any 8-x slot
that happens to look financial; the two numbering schemes are unrelated.

RECONSTRUCTED 2026-11-13: this file (never committed to git) was overwritten by an unreviewed
external rewrite earlier this session and no backup existed anywhere (checked: git history, the
bytecode cache, editor history - nothing recoverable). The exact original slot names and
descriptions for the 18 "8-x" slots are NOT recoverable and are not guessed at here. What IS
rebuilt, faithfully, is every piece of BEHAVIOR the rest of this codebase and its test suite
actually depend on - derived directly from tests/test_governance.py's RegistryTests and
tests/test_agents_runtime.py's isolation test, both of which pin down the exact required
structure: the PUBLIC/FINANCE/MEDICAL/EMPLOYER/DOSSIER_1..4 data-class tags, the IsolationError
exception, 18 slots where 8-11 and 8-12 each expand into 5 sub-agents (8-11a..e, 8-12a..e) and
8-13/8-14 are deliberately left unresolved (no deployed agent), and the specific isolation
denials those tests assert. Any slot name/allowed_data combination NOT pinned down by a test is a
placeholder (least-privilege: public data only) rather than the verbatim original, and is marked
PLACEHOLDER below so it is not mistaken for restored history.
"""
from __future__ import annotations

from dataclasses import dataclass

from .agent_contract import ContractError, parse_output

PUBLIC = "public"
FINANCE = "finance"
MEDICAL = "medical"
EMPLOYER = "employer"
DOSSIER_1 = "dossier_1"
DOSSIER_2 = "dossier_2"
DOSSIER_3 = "dossier_3"
DOSSIER_4 = "dossier_4"
_DOSSIER_TAGS = (DOSSIER_1, DOSSIER_2, DOSSIER_3, DOSSIER_4)

SLOTS = tuple(f"8-{n}" for n in range(1, 19))


class IsolationError(PermissionError):
    # A PermissionError subclass on purpose: core/apex/kernel/dossier.py's _authorise() catches
    # (KeyError, PermissionError) from agents_registry.get() and turns it into its own
    # "AGENT_UNKNOWN_OR_UNRESOLVED" denial reason - this must be catchable there.
    pass


@dataclass(frozen=True)
class LegacyAgent:
    agent_id: str | None          # None only for an unresolved slot (8-13, 8-14)
    slot: str
    name: str
    allowed_data: frozenset
    max_dossier_tier: int = 0     # highest DOSSIER_n / personal_dossier tier this agent may read; 0 = none
    key_prefixes: tuple = ()      # non-empty only for 8-8 (kernel/dossier.py's own docstring notes this)


def _dossier_up_to(tier: int) -> frozenset:
    if not 0 <= tier <= 4:
        raise ValueError("tier out of range")
    return frozenset(_DOSSIER_TAGS[:tier])


def _agent(agent_id, slot, name, extra=(), dossier_tier=0, key_prefixes=()):
    return LegacyAgent(agent_id, slot, name, frozenset({PUBLIC, *extra}) | _dossier_up_to(dossier_tier),
                        max_dossier_tier=dossier_tier, key_prefixes=key_prefixes)


_REGISTRY = [
    # Specific isolation behaviour below is REQUIRED (pinned by tests). Names marked PLACEHOLDER
    # are not the original wording - only the isolation boundary is restored, not the prose.
    _agent("8-1", "8-1", "PLACEHOLDER: Personal Context", dossier_tier=1),             # allows DOSSIER_1, denies DOSSIER_2 (tested)
    _agent("8-2", "8-2", "PLACEHOLDER: slot 8-2"),
    _agent("8-3", "8-3", "PLACEHOLDER: slot 8-3"),                                     # denies DOSSIER_1 (tested) -> tier 0
    _agent("8-4", "8-4", "PLACEHOLDER: slot 8-4"),
    _agent("8-5", "8-5", "PLACEHOLDER: slot 8-5"),
    _agent("8-6", "8-6", "PLACEHOLDER: slot 8-6"),
    _agent("8-7", "8-7", "PLACEHOLDER: slot 8-7"),
    # 8-8: real dossier.py test requires tier<=3 (reads lang.* at tier 3, denied DOSSIER_4/tier4)
    # AND a key-prefix restriction - kernel/dossier.py's own docstring says 8-8 is the one agent
    # with key_prefixes. Allowed prefix pinned by test: "lang." (profile.* is denied there).
    _agent("8-8", "8-8", "PLACEHOLDER: slot 8-8 (companion addendum calls this role 'Loneliness/Energy', unrelated to A-8 Financial)",
           dossier_tier=3, key_prefixes=("lang.",)),
    _agent("8-9", "8-9", "PLACEHOLDER: slot 8-9", dossier_tier=2),   # must read a tier-2 dossier key (tested)
    _agent("8-10", "8-10", "PLACEHOLDER: slot 8-10"),
]
_REGISTRY += [_agent(f"8-11{c}", "8-11", f"PLACEHOLDER: slot 8-11{c}") for c in "abcde"]   # denies FINANCE(a)/MEDICAL(c) (tested) -> public only
_REGISTRY += [_agent(f"8-12{c}", "8-12", f"PLACEHOLDER: slot 8-12{c}") for c in "abcde"]   # denies DOSSIER_3 (8-12a, tested) -> public only
_REGISTRY += [
    LegacyAgent(None, "8-13", "PLACEHOLDER: slot 8-13 (unresolved - no deployed agent)", frozenset(), 0),
    LegacyAgent(None, "8-14", "PLACEHOLDER: slot 8-14 (unresolved - no deployed agent)", frozenset(), 0),
    _agent("8-15", "8-15", "PLACEHOLDER: slot 8-15"),      # denies EMPLOYER (tested) -> public only
    _agent("8-16", "8-16", "PLACEHOLDER: slot 8-16"),
    _agent("8-17", "8-17", "PLACEHOLDER: slot 8-17"),
    _agent("8-18", "8-18", "PLACEHOLDER: slot 8-18"),
]

REGISTRY = tuple(_REGISTRY)
assert {a.slot for a in REGISTRY} == set(SLOTS) and len(SLOTS) == 18


def get(key: str) -> LegacyAgent:
    for a in REGISTRY:
        if a.agent_id == key:
            return a
    for a in REGISTRY:
        if a.slot == key:
            raise IsolationError("AGENT_UNRESOLVED_SOURCE")
    raise IsolationError(f"Unknown agent or slot: {key}")


def check_inputs(agent_id: str, data_classes, data_source: str = "personal") -> bool:
    if data_source == "corporate":
        raise IsolationError("CORPORATE_SOURCE_DENIED")
    agent = get(agent_id)
    denied = frozenset(data_classes) - agent.allowed_data
    if denied:
        raise IsolationError("DATA_CLASS_DENIED:" + ",".join(sorted(denied)))
    return True


def validate_output(agent_id: str, payload: dict):
    result = parse_output(payload)
    if result.agent_id != agent_id:
        raise ContractError(f"Output agent_id {result.agent_id!r} does not match expected {agent_id!r}")
    return result
