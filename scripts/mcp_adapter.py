#!/usr/bin/env python3
"""Kernel-bound MCP adapter: exposes exactly two tools, `search` and `execute`, to a locally
spawned MCP client (e.g. a Claude Desktop extension talking stdio) - nothing else.

What this is NOT, on purpose:
  - Not a network service. This speaks newline-delimited JSON-RPC over stdin/stdout only, the
    transport a local MCP stdio client (Claude Desktop extension / `.mcpb`) actually uses. Mounting
    an HTTP/ASGI endpoint on api.apexcorelab.uk is a separate, explicitly deferred decision - it
    needs the console_server.py ASGI/WSGI question resolved first (see that file's own notes), and
    it changes what's reachable from the internet, which this project does not do without a
    specific, reviewed step.
  - Not the real MCP Python SDK. That package is not installed (same reasoning as `langgraph` and
    `uvicorn` elsewhere in this repo: it would need `pip install --break-system-packages` on this
    Debian-managed Python, and the actual surface needed - two fixed tools, no sampling/resources/
    prompts negotiation - does not need the SDK). This hand-rolls the minimal JSON-RPC 2.0 subset
    (`initialize`, `tools/list`, `tools/call`) that subset needs.
  - Not eval, SQL, a shell, or a URL fetcher. `execute` only ever calls two existing, already-
    reviewed kernel methods (ActionGateway.submit / ActionGateway.execute). There is no third code
    path, so there is nothing here that can run arbitrary code or reach an arbitrary host.

Safety properties (why this is safe to let an LLM call via MCP):
  - `search` is read-only: it lists the kind schemas already defined in kernel/gateway.py's
    DEFAULT_KINDS (domains, required fields, whether an adapter is configured). No secrets, no
    live personal data, no network call.
  - `execute` with action="propose" calls ActionGateway.submit(), i.e. kernel/approvals.py's
    ApprovalBook.propose(). That only ever creates a PENDING/DEFERRED row for a human to review -
    it cannot itself cause anything to happen.
  - `execute` with action="dispatch" calls ActionGateway.execute(proposal_id), which refuses
    unless that proposal's state is already APPROVED - and a human approval can ONLY be produced
    by ApprovalBook.issue()/approve(), which structurally reject any identity starting with
    "agent:" (ApprovalError("HUMAN_IDENTITY_REQUIRED") / self-approval checks). This adapter's
    proposer identity is always "agent:mcp-claude", so it can never approve its own (or any)
    proposal - the kernel enforces this, not this file's discipline.
  - Every call still goes through ActionGateway.execute()'s own re-checks (kill state, durable
    stop, adapter configured, budget) at dispatch time, unchanged from every other caller.

Run (manual, for testing the stdio loop locally - not installed as a service):
  python3 scripts/mcp_adapter.py
reads JSON-RPC requests from stdin, one per line, writes responses to stdout, one per line.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel.approvals import ApprovalBook, ApprovalError  # noqa: E402
from apex.kernel.budget import Budget, BudgetDenied            # noqa: E402
from apex.kernel.gateway import ActionGateway, GatewayError     # noqa: E402
from apex.kernel.memory import Ledger                           # noqa: E402
from apex.kernel.schema import identifier                       # noqa: E402

PROPOSER_IDENTITY = "agent:mcp-claude"       # always starts with "agent:" - see module docstring


class ExistingApexPorts:
    """Thin, typed wrapper around the already-reviewed ApprovalBook/ActionGateway. No new state,
    no new table, no new adapter - this only calls methods that exist and are tested elsewhere."""

    def __init__(self, gateway: ActionGateway):
        self.gateway = gateway

    def search(self, query: str | None = None) -> list[dict]:
        out = []
        for kind, spec in self.gateway.kinds.items():
            if query and query.lower() not in kind.lower():
                continue
            out.append({
                "kind": kind,
                "domains": sorted(spec.domains),
                "fields": {name: typ.__name__ for name, typ in spec.fields.items()},
                "adapter": spec.adapter,                 # None = local record only, never dispatched externally
                "requires_human_approval_before_dispatch": spec.adapter is not None,
            })
        return out

    def execute(self, action: str, **kwargs) -> dict:
        if action == "propose":
            return self._propose(**kwargs)
        if action == "dispatch":
            return self._dispatch(**kwargs)
        raise GatewayError("UNKNOWN_CAPABILITY")

    def _propose(self, kind: str = None, domain: str = None, payload: dict = None,
                 evidence_ids: list = None, commentary: str = None, **extra) -> dict:
        if extra:
            raise GatewayError("UNKNOWN_FIELD:" + ",".join(sorted(extra)))
        if not isinstance(kind, str) or not isinstance(domain, str) or not isinstance(payload, dict) \
                or not isinstance(evidence_ids, list):
            raise GatewayError("PROPOSE_FIELDS_REQUIRED:kind,domain,payload,evidence_ids")
        proposal_id = identifier(f"mcp.{int(time.time() * 1000)}"[:48])
        state = self.gateway.submit(proposal_id, domain, kind, PROPOSER_IDENTITY, payload,
                                     evidence_ids, commentary=commentary)
        return {"proposal_id": proposal_id, "state": state}

    def _dispatch(self, proposal_id: str = None, **extra) -> dict:
        # Deliberately takes nothing but an id: no "actor" or "approval" field is accepted here,
        # because accepting one would let a caller claim an approval instead of the kernel
        # checking its own ApprovalBook state - that is the "deny additional actor/approval
        # fields" requirement from the brief, enforced by simply never parsing such a field.
        if extra:
            raise GatewayError("UNKNOWN_FIELD:" + ",".join(sorted(extra)))
        if not isinstance(proposal_id, str):
            raise GatewayError("DISPATCH_FIELDS_REQUIRED:proposal_id")
        return {"proposal_id": proposal_id, "state": self.gateway.execute(proposal_id)}


TOOLS = [
    {"name": "search", "description": "List authorized action kinds (schema only, read-only, no live data).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "execute", "description": "Typed dispatch only: propose a reviewable action, or finalise one a "
                                        "human already approved in the console. Never arbitrary code.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["propose", "dispatch"]},
         "kind": {"type": "string"}, "domain": {"type": "string"}, "payload": {"type": "object"},
         "evidence_ids": {"type": "array"}, "commentary": {"type": "string"},
         "proposal_id": {"type": "string"}}, "required": ["action"]}},
]


def _rpc_dispatch(ports: ExistingApexPorts, request: dict) -> dict | None:
    req_id, method = request.get("id"), request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                       "serverInfo": {"name": "apex-kernel-adapter", "version": "1"},
                       "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if name == "search":
                result = {"content": [{"type": "text", "text": json.dumps(ports.search(args.get("query")))}]}
            elif name == "execute":
                result = {"content": [{"type": "text", "text": json.dumps(ports.execute(**args))}]}
            else:
                return _error(req_id, -32601, f"UNKNOWN_TOOL:{name}")
        elif method == "notifications/initialized":
            return None            # notification, no response expected
        else:
            return _error(req_id, -32601, f"UNKNOWN_METHOD:{method}")
    except (GatewayError, ApprovalError, BudgetDenied, ValueError) as exc:
        return _error(req_id, -32000, f"{type(exc).__name__}:{exc}")
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def serve_stdio(root: Path = ROOT) -> None:
    from apex.google_web import protected_json
    secret = protected_json("/etc/apex/approvals-runtime.json")["approval_secret"].encode()
    with Ledger(root) as ledger:
        budget = Budget(ledger)
        gateway = ActionGateway(ledger, ApprovalBook(ledger, secret), budget)
        ports = ExistingApexPorts(gateway)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                print(json.dumps(_error(None, -32700, "PARSE_ERROR")), flush=True)
                continue
            response = _rpc_dispatch(ports, request)
            if response is not None:
                print(json.dumps(response), flush=True)


if __name__ == "__main__":
    serve_stdio()
