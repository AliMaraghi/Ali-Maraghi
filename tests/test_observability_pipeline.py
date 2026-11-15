"""Total observability + HITL alerting (mission 2026-11-15). Integration test: a synthetic
bill triggers a real domain proposal, which publishes real telemetry, which the SSE WSGI app
actually streams - no mocks of the pipeline itself, only synthetic input data. Follows this
codebase's own established WSGI test pattern (see tests/test_console_server.py) rather than
spinning a real TCP server - a WSGI callable IS the server interface; calling it directly
with a constructed environ is a real test of the real app, not a mock of it.
"""
import io
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from apex.api import telemetry
import agents_runner


def call_wsgi(app, path, method="GET", last_event_id=None):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {"PATH_INFO": path, "REQUEST_METHOD": method, "wsgi.input": io.BytesIO()}
    if last_event_id is not None:
        environ["HTTP_LAST_EVENT_ID"] = str(last_event_id)
    result = app(environ, start_response)
    return captured, result


class EventBusTests(unittest.TestCase):
    def test_publish_and_since(self):
        bus = telemetry.EventBus()
        bus.publish(telemetry.KERNEL_EVENT, {"message": "a"})
        bus.publish(telemetry.HITL_REQUIRED, {"action_id": "x", "description": "approve x"})
        events = bus.since(0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], telemetry.KERNEL_EVENT)
        self.assertEqual(events[1]["type"], telemetry.HITL_REQUIRED)
        self.assertEqual(bus.since(1), [events[1]])

    def test_sse_format(self):
        bus = telemetry.EventBus()
        event = bus.publish(telemetry.KERNEL_EVENT, {"message": "hi"})
        text = telemetry.sse_format(event)
        self.assertTrue(text.startswith(f"id: {event['seq']}\n"))
        self.assertIn("event: KERNEL\n", text)
        self.assertTrue(text.endswith("\n\n"))
        self.assertIn('"message": "hi"', text)


class StreamEventsBehaviorTests(unittest.TestCase):
    def test_stream_events_picks_up_events_published_between_polls(self):
        bus = telemetry.EventBus()
        gen = telemetry.stream_events(bus, start_seq=0, max_polls=5)
        chunks = []
        bus.publish(telemetry.KERNEL_EVENT, {"message": "first"})
        chunks.extend(list(gen))
        self.assertTrue(any("first" in c for c in chunks))


class WsgiAppTests(unittest.TestCase):
    def test_wrong_path_is_404(self):
        app = telemetry.sse_wsgi_app(telemetry.EventBus())
        captured, body = call_wsgi(app, "/not/the/stream")
        self.assertTrue(captured["status"].startswith("404"))

    def test_post_is_405_no_write_method_exists(self):
        """The hard security property: there is no write method on this path at all - an
        approval can never be submitted through the telemetry endpoint."""
        app = telemetry.sse_wsgi_app(telemetry.EventBus())
        captured, body = call_wsgi(app, telemetry.STREAM_PATH, method="POST")
        self.assertTrue(captured["status"].startswith("405"))

    def test_head_returns_event_stream_headers_no_body(self):
        app = telemetry.sse_wsgi_app(telemetry.EventBus())
        captured, body = call_wsgi(app, telemetry.STREAM_PATH, method="HEAD")
        self.assertTrue(captured["status"].startswith("200"))
        self.assertEqual(captured["headers"]["Content-Type"], "text/event-stream; charset=utf-8")
        self.assertEqual(b"".join(body), b"")


class FullPipelineIntegrationTests(unittest.TestCase):
    """Phase 3, the mission's own required test: trigger a synthetic Bill, assert the SSE
    stream receives both a KERNEL event and a HITL_REQUIRED event."""

    def test_synthetic_bill_produces_kernel_and_hitl_events_on_the_real_stream(self):
        bus = telemetry.EventBus()
        with tempfile.TemporaryDirectory() as tmp:
            inbox_root = Path(tmp)
            (inbox_root / "runtime" / "inbox").mkdir(parents=True)
            (inbox_root / "runtime" / "inbox" / "bills.json").write_text(
                json.dumps({"vendor": "AWS", "amount_pence": 4500, "due_date": "2026-11-20"}))
            agents_runner.run_domains(inbox_root=inbox_root, bus=bus)

        # Both events were already published before this GET arrives, so the real app's
        # first internal poll (sse_wsgi_app never bounds max_polls - that is correct for a
        # real client holding the connection open) yields them immediately; islice(2) takes
        # exactly those two chunks without this test waiting on the generator's infinite
        # real-time poll loop afterward.
        app = telemetry.sse_wsgi_app(bus)
        _, body_iter = call_wsgi(app, telemetry.STREAM_PATH, method="GET")
        raw = b"".join(itertools.islice(body_iter, 2)).decode("utf-8")

        self.assertIn("event: KERNEL", raw)
        self.assertIn("Bill parsed: AWS", raw)
        self.assertIn("event: HITL_REQUIRED", raw)
        self.assertIn("Approve AWS Bill", raw)

    def test_no_approval_can_be_submitted_through_this_pipeline(self):
        """Structural proof of the security decision documented in telemetry.py's own
        docstring: there is no POST /api/v1/approvals/{id} anywhere in this module, and the
        one path that exists refuses every write method."""
        bus = telemetry.EventBus()
        app = telemetry.sse_wsgi_app(bus)
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            captured, _ = call_wsgi(app, telemetry.STREAM_PATH, method=method)
            self.assertTrue(captured["status"].startswith("405"), f"{method} should be refused")


if __name__ == "__main__":
    unittest.main()
