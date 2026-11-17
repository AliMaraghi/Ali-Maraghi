"""Static guard for evolved candidates. A candidate that fails here is never executed."""
from __future__ import annotations

import ast

START, END = "# EVOLVE-BLOCK-START", "# EVOLVE-BLOCK-END"
MAX_BLOCK_CHARS = 4000
ALLOWED_NODES = (
    ast.Module, ast.Assign, ast.Name, ast.Store, ast.Load, ast.Constant, ast.Dict, ast.List, ast.Tuple,
    ast.UnaryOp, ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Expr,
)
ALLOWED_TARGETS = frozenset({"EVENT_KEYWORD_WEIGHTS", "CONTENT_ANGLE_WEIGHTS", "ROUTING", "WEEKEND_BONUS"})


def split(source: str) -> tuple[str, str, str]:
    if source.count(START) != 1 or source.count(END) != 1 or source.index(START) > source.index(END):
        raise ValueError("exactly one EVOLVE-BLOCK is required")
    head, rest = source.split(START, 1)
    block, tail = rest.split(END, 1)
    return head, block, tail


def violations(baseline: str, candidate: str) -> list[str]:
    """Empty list = safe to evaluate. Data assignments only: no imports, calls, attributes,
    names other than the four targets, loops, functions or comprehensions."""
    try:
        base_head, _, base_tail = split(baseline)
        head, block, tail = split(candidate)
    except ValueError as exc:
        return [f"markers: {exc}"]
    found: list[str] = []
    if head != base_head or tail != base_tail:
        found.append("code outside the EVOLVE-BLOCK was changed")
    if len(block) > MAX_BLOCK_CHARS:
        found.append("block too large")
    try:
        tree = ast.parse(block)
    except SyntaxError as exc:
        return found + [f"syntax error in block: {exc.msg}"]
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            found.append(f"forbidden syntax: {type(node).__name__}")
        elif isinstance(node, ast.Name):
            if node.id not in ALLOWED_TARGETS:
                found.append(f"unknown name: {node.id}")
            elif isinstance(node.ctx, ast.Store):
                assigned.add(node.id)
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str)):
            found.append("only numbers and strings are allowed as values")
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            found.append("booleans are not allowed as values")
    if assigned != ALLOWED_TARGETS:
        found.append("the block must assign exactly: " + ", ".join(sorted(ALLOWED_TARGETS)))
    return sorted(set(found))
