"""Proposes candidates by nudging numbers inside the EVOLVE-BLOCK. No model, no cost.

Seeded, so a run can be reproduced. Only numeric literals between the markers are touched;
guard.py still checks every candidate before it is ever executed.
"""
from __future__ import annotations

import random
import re

from . import guard

NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")


def mutate(source: str, rng: random.Random, rate: float = 0.35) -> str:
    head, block, tail = guard.split(source)
    out = []
    for line in block.splitlines(keepends=True):
        if line.lstrip().startswith("ROUTING"):       # integer thresholds: scale, keep integers
            line = NUMBER.sub(lambda m: m.group(0) if "." in m.group(0) or rng.random() > rate
                              else str(max(100, int(int(m.group(0)) * rng.uniform(0.7, 1.3)))), line)
        else:
            line = NUMBER.sub(lambda m: m.group(0) if rng.random() > rate
                              else f"{max(-5.0, min(5.0, float(m.group(0)) + rng.choice((-1.0, -0.5, 0.5, 1.0)))):.1f}", line)
        out.append(line)
    return head + guard.START + "".join(out) + guard.END + tail
