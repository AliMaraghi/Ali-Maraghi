"""Offline regression tests; no database, HTTP server, Docker, or paid service.

FastAPI is unavailable in the development image. Route functions are exercised
with a minimal import stub; this does not substitute for ASGI integration tests.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, Mock, call, patch

from apex import monitor, rss, storage
from apex.discovery import cli


class StorageSafetyTests(unittest.TestCase):
    def test_readiness_is_read_only_and_never_creates_schema(self):
        database = MagicMock()
        database.execute.return_value.fetchone.return_value = {'ready': 1}
        with patch.object(storage, 'connection') as connect:
            connect.return_value.__enter__.return_value = database
            self.assertTrue(storage.database_ready())
        self.assertEqual(database.execute.call_args_list, [
            call('SET TRANSACTION READ ONLY'), call('SELECT 1 AS ready'),
        ])

    def test_failed_readiness_is_not_reported_ready(self):
        database = MagicMock()
        database.execute.return_value.fetchone.return_value = None
        with patch.object(storage, 'connection') as connect:
            connect.return_value.__enter__.return_value = database
            self.assertFalse(storage.database_ready())

    def test_connection_has_connect_and_statement_timeouts(self):
        driver = types.ModuleType('psycopg')
        rows = types.ModuleType('psycopg.rows')
        rows.dict_row = object()
        driver.connect = Mock()
        with patch.dict('sys.modules', {'psycopg': driver, 'psycopg.rows': rows}):
            with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://dev.invalid/apex'}):
                storage.connection()
        self.assertEqual(driver.connect.call_args.kwargs['connect_timeout'], 5)
        self.assertEqual(driver.connect.call_args.kwargs['options'], '-c statement_timeout=5000')

    def test_health_route_delegates_to_readiness_and_hides_errors(self):
        framework = types.ModuleType('fastapi')
        responses = types.ModuleType('fastapi.responses')
        app = Mock()
        app.get.side_effect = lambda *args, **kwargs: lambda function: function
        framework.FastAPI = Mock(return_value=app)
        responses.HTMLResponse = type('HTMLResponse', (), {})
        responses.JSONResponse = lambda **kwargs: types.SimpleNamespace(**kwargs)
        path = cli.WORKSPACE_ROOT / 'core/apex/app.py'
        spec = importlib.util.spec_from_file_location('apex._legacy_test_app', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'fastapi': framework, 'fastapi.responses': responses}):
            spec.loader.exec_module(module)
        with patch.object(module, 'database_ready', return_value=True) as check:
            self.assertEqual(module.healthz(), {'status': 'ok', 'database': 'connected'})
            check.assert_called_once_with()
        for outcome in [False, RuntimeError('private diagnostic')]:
            checker = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
            with patch.object(module, 'database_ready', checker):
                response = module.healthz()
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.content, {'status': 'degraded', 'database': 'unavailable'})


class FeedSafetyTests(unittest.TestCase):
    def test_redirects_are_rejected_before_any_followup_request(self):
        for destination in ['http://127.0.0.1/', 'https://other.invalid/', 'https://arxiv.org/']:
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                monitor.NoRedirect().redirect_request(None, None, 302, 'Found', {}, destination)

    def test_foreign_source_rejected_without_opening(self):
        with patch.object(monitor.urllib.request, 'build_opener') as opener:
            with self.assertRaises(ValueError):
                monitor.fetch_feed('https://foreign.invalid/feed')
            opener.assert_not_called()

    def fake_response(self, chunks):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read1.side_effect = chunks
        return response

    def test_fetch_uses_timeout_and_bounded_chunk_reads(self):
        response = self.fake_response([b'abc', b''])
        with patch.object(monitor.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            self.assertEqual(monitor.fetch_feed('https://arxiv.org/feed'), b'abc')
            self.assertEqual(build.return_value.open.call_args.kwargs['timeout'], 12)
        self.assertTrue(all(args.args[0] <= 65536 for args in response.read1.call_args_list))
        response.__exit__.assert_called_once()

    def test_oversized_response_rejected_and_closed(self):
        response = self.fake_response([b'abcde'])
        with patch.object(monitor, 'MAX_FEED_BYTES', 4):
            with patch.object(monitor.urllib.request, 'build_opener') as build:
                build.return_value.open.return_value = response
                with self.assertRaises(ValueError):
                    monitor.fetch_feed('https://arxiv.org/feed')
        response.__exit__.assert_called_once()

    def test_slow_response_rejected_between_reads(self):
        response = self.fake_response([b'a'])
        with patch.object(monitor.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            with patch.object(monitor.time, 'monotonic', side_effect=[0, 0, 13]):
                with self.assertRaises(TimeoutError):
                    monitor.fetch_feed('https://arxiv.org/feed')
        self.assertEqual(response.read1.call_count, 1)

    def test_failed_fetch_never_writes_or_logs_response_content(self):
        with patch.object(monitor, 'SOURCES', {'test': 'https://arxiv.org/feed'}):
            with patch.object(monitor, 'fetch_feed', side_effect=ValueError('private diagnostic')):
                with patch.object(monitor, 'upsert') as save:
                    with self.assertLogs('apex.monitor', level='WARNING') as logs:
                        monitor.poll_once()
                    save.assert_not_called()
                    self.assertNotIn('private diagnostic', '\n'.join(logs.output))

    def test_xml_rejects_entities_oversize_and_invalid_limits(self):
        for raw in [b'<!DOCTYPE rss [<!ENTITY x "data">]><rss/>', b'\x00<rss/>', b'x' * (rss.MAX_FEED_BYTES + 1)]:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                rss.extract_items(raw)
        for limit in [0, -1, True, 1001, '3']:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                rss.extract_items(b'<rss/>', limit=limit)

    def test_atom_normalization_and_rss_filtering_still_work(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Paper</title><id>http://arxiv.org/abs/1234.5678</id></entry></feed>'
        self.assertEqual(rss.extract_items(atom), [('Paper', 'https://arxiv.org/abs/1234.5678')])
        feed = b'<rss><channel><item><title>Paper</title><link>https://arxiv.org/abs/1234</link></item><item><title>Bad</title><link>https://foreign.invalid/</link></item></channel></rss>'
        self.assertEqual(rss.extract_items(feed), [('Paper', 'https://arxiv.org/abs/1234')])

    def test_url_control_characters_and_empty_credentials_rejected(self):
        for url in ['https://@arxiv.org/a', 'https://arxiv.org/a\n', 'https://arxiv.org/\ta', ' https://arxiv.org/a']:
            with self.subTest(url=url):
                self.assertFalse(rss.allowed_link(url))


class OfflineInputSafetyTests(unittest.TestCase):
    def setUp(self):
        (cli.WORKSPACE_ROOT / 'work').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='legacy-test-', dir=cli.WORKSPACE_ROOT / 'work')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'signal.json'
        self.valid = {'title': 'Synthetic paper', 'url': 'https://arxiv.org/abs/0000.00000', 'synthetic': True}

    def write_input(self, value):
        self.input.write_text(json.dumps(value), encoding='utf-8')

    def test_valid_regular_file_is_accepted(self):
        self.write_input(self.valid)
        result = cli.read_offline_input(self.input)
        self.assertEqual(result.title, self.valid['title'])
        self.assertTrue(result.synthetic)

    def test_invalid_types_and_unknown_fields_rejected(self):
        for value in [[], {**self.valid, 'synthetic': 'false'}, {**self.valid, 'title': 1}, {**self.valid, 'source': []}, {**self.valid, 'verified': True}]:
            self.write_input(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                cli.read_offline_input(self.input)

    def test_oversized_file_rejected(self):
        self.input.write_bytes(b' ' * (cli.MAX_INPUT_BYTES + 1))
        with self.assertRaises(ValueError):
            cli.read_offline_input(self.input)

    def test_symlink_file_and_parent_rejected(self):
        self.write_input(self.valid)
        link = self.root / 'link.json'
        link.symlink_to(self.input)
        with self.assertRaises(OSError):
            cli.read_offline_input(link)
        directory_link = self.root / 'linked-directory'
        directory_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            cli.read_offline_input(directory_link / 'signal.json')

    def test_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.input)
        with self.assertRaises(ValueError):
            cli.read_offline_input(self.input)

    def test_outside_workspace_and_parent_traversal_rejected_before_open(self):
        for path in [Path('/tmp/apex-forbidden-input.json'), cli.WORKSPACE_ROOT / '..' / 'input.json']:
            with self.subTest(path=path), patch.object(cli.os, 'open') as open_file:
                with self.assertRaises(ValueError):
                    cli.read_offline_input(path)
                open_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
