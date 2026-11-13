"""scripts/mcp_adapter.py: the kernel-bound search/execute MCP tool surface, fully offline.

Exercises ExistingApexPorts directly (no stdio, no subprocess) plus the JSON-RPC dispatch
function, against a real in-memory-equivalent Ledger/ApprovalBook/ActionGateway - the same
objects every other kernel test uses, not mocks of the safety-relevant parts.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "core"))

import mcp_adapter  # noqa: E402
from apex.kernel.approvals import ApprovalBook  # noqa: E402
from apex.kernel.budget import Budget  # noqa: E402
from apex.kernel.gateway import ActionGateway, GatewayError  # noqa: E402
from apex.kernel.memory import Ledger  # noqa: E402


class PortsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.budget = Budget(self.ledger)
        self.book = ApprovalBook(self.ledger, b"k" * 32)
        self.gateway = ActionGateway(self.ledger, self.book, self.budget)
        self.ports = mcp_adapter.ExistingApexPorts(self.gateway)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    # ---- search: read-only schema listing -----------------------------------
    def test_search_lists_known_kinds_without_touching_anything(self):
        kinds = {row["kind"] for row in self.ports.search()}
        self.assertIn("research_brief_proposal", kinds)
        self.assertIn("record_decision", kinds)

    def test_search_filters_by_query(self):
        kinds = {row["kind"] for row in self.ports.search("research")}
        self.assertEqual(kinds, {"research_brief_proposal"})

    def test_search_marks_local_record_kinds_as_not_requiring_adapter(self):
        row = next(r for r in self.ports.search() if r["kind"] == "research_brief_proposal")
        self.assertIsNone(row["adapter"])
        self.assertFalse(row["requires_human_approval_before_dispatch"])

    # ---- execute: propose --------------------------------------------------
    def test_propose_creates_a_pending_proposal(self):
        result = self.ports.execute("propose", kind="record_decision", domain="opportunity",
                                     payload={"note": "test"}, evidence_ids=["ev1"])
        self.assertEqual(result["state"], "PENDING")
        self.assertEqual(self.book.state(result["proposal_id"]), "PENDING")

    def test_propose_rejects_unknown_kind(self):
        with self.assertRaises(GatewayError):
            self.ports.execute("propose", kind="not_a_real_kind", domain="opportunity",
                                payload={}, evidence_ids=["ev1"])

    def test_propose_rejects_extra_fields(self):
        with self.assertRaises(GatewayError):
            self.ports.execute("propose", kind="record_decision", domain="opportunity",
                                payload={"note": "x"}, evidence_ids=["ev1"], actor="someone_else")

    def test_propose_rejects_missing_fields(self):
        with self.assertRaises(GatewayError):
            self.ports.execute("propose", kind="record_decision")

    # ---- execute: dispatch - the "model cannot approve itself" guarantee --
    def test_dispatch_on_a_not_yet_approved_proposal_is_refused(self):
        proposed = self.ports.execute("propose", kind="record_decision", domain="opportunity",
                                       payload={"note": "test"}, evidence_ids=["ev1"])
        with self.assertRaises(GatewayError):
            self.ports.execute("dispatch", proposal_id=proposed["proposal_id"])
        self.assertEqual(self.book.state(proposed["proposal_id"]), "PENDING")

    def test_the_mcp_identity_can_never_issue_or_approve_its_own_proposal(self):
        proposed = self.ports.execute("propose", kind="record_decision", domain="opportunity",
                                       payload={"note": "test"}, evidence_ids=["ev1"])
        # The kernel itself refuses an "agent:" identity as an approver - not this adapter's
        # discipline. This is the actual enforcement point the brief calls "a model cannot
        # approve itself".
        from apex.kernel.approvals import ApprovalError
        with self.assertRaises(ApprovalError):
            self.book.issue(proposed["proposal_id"], mcp_adapter.PROPOSER_IDENTITY)

    def test_dispatch_succeeds_once_a_human_has_actually_approved(self):
        proposed = self.ports.execute("propose", kind="record_decision", domain="opportunity",
                                       payload={"note": "test"}, evidence_ids=["ev1"])
        token = self.book.issue(proposed["proposal_id"], "owner")
        self.book.approve(proposed["proposal_id"], token, "owner")
        result = self.ports.execute("dispatch", proposal_id=proposed["proposal_id"])
        self.assertEqual(result["state"], "EXECUTED")

    def test_dispatch_rejects_extra_fields(self):
        with self.assertRaises(GatewayError):
            self.ports.execute("dispatch", proposal_id="whatever", approval="forged")

    def test_unknown_action_is_refused(self):
        with self.assertRaises(GatewayError):
            self.ports.execute("eval", code="1+1")


class JsonRpcTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.ports = mcp_adapter.ExistingApexPorts(
            ActionGateway(self.ledger, ApprovalBook(self.ledger, b"k" * 32), Budget(self.ledger)))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_initialize(self):
        resp = mcp_adapter._rpc_dispatch(self.ports, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(resp["result"]["serverInfo"]["name"], "apex-kernel-adapter")

    def test_tools_list_exposes_exactly_search_and_execute(self):
        resp = mcp_adapter._rpc_dispatch(self.ports, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual({t["name"] for t in resp["result"]["tools"]}, {"search", "execute"})

    def test_tools_call_search(self):
        resp = mcp_adapter._rpc_dispatch(self.ports, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                       "params": {"name": "search", "arguments": {}}})
        self.assertIn("content", resp["result"])

    def test_unknown_tool_is_an_error_not_a_crash(self):
        resp = mcp_adapter._rpc_dispatch(self.ports, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                                       "params": {"name": "shell", "arguments": {}}})
        self.assertIn("error", resp)

    def test_notification_gets_no_response(self):
        resp = mcp_adapter._rpc_dispatch(self.ports, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(resp)


if __name__ == "__main__":
    unittest.main()
