"""Loads evolution/config.yaml and clamps it to built-in safety floors."""
from __future__ import annotations

import os
import re
from pathlib import Path

FLAG = "ENABLE_EVOLUTION_SANDBOX"
PATH = Path(__file__).with_name("config.yaml")
# name: (default, clamp) - clamp pulls any configured value back to the safe side.
_RULES = {
    "min_improvement": (0.05, lambda v: max(0.05, min(float(v), 1.0))),
    "min_real_outcomes": (30, lambda v: max(30, int(v))),
    "cpu_seconds": (5, lambda v: max(1, min(int(v), 5))),
    "candidates_per_run": (20, lambda v: max(1, min(int(v), 50))),
    "monthly_cap_pence": (500, lambda v: max(0, min(int(v), 500))),
}


def enabled() -> bool:
    """Off unless ENABLE_EVOLUTION_SANDBOX is explicitly true/1/on."""
    return os.environ.get(FLAG, "false").strip().lower() in ("true", "1", "on", "yes")


def load(path: Path = PATH) -> dict[str, float]:
    raw: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([a-z_]+)\s*:\s*([0-9.]+)\s*(?:#.*)?$", line)
            if match:
                raw[match.group(1)] = match.group(2)
    out: dict[str, float] = {}
    for name, (default, clamp) in _RULES.items():
        try:
            out[name] = clamp(raw.get(name, default))
        except ValueError:
            out[name] = default
    return out
