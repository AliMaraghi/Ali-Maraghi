import unittest
from unittest.mock import patch, Mock
from apex.google_http import request_path, fetch
from apex.gmail_sync import METADATA_HEADERS


class GoogleHTTPTests(unittest.TestCase):
    def test_sent_and_metadata(self):
        self.assertIn('labelIds=SENT', request_path('messages', {'maxResults':20, 'labelIds':['SENT']}))
        self.assertIn('format=metadata', request_path('threads/abc123', {'format':'metadata','metadataHeaders':list(METADATA_HEADERS)}))

    def test_reject_unbounded_and_unsafe_operations(self):
        for resource, params in [('https://evil.test', {}), ('messages/send', {}),
                ('threads', {}), ('messages', {'maxResults':True}),
                ('messages', {'maxResults':21}), ('threads/abc', {'format':'full'}),
                ('messages', {'maxResults':20, 'q':'private'}), ('../profile', {})]:
            with self.subTest(resource=resource, params=params), self.assertRaises(ValueError):
                request_path(resource, params)

    @patch('apex.google_http.resolve_public', return_value=(2, '8.8.8.8'))
    @patch('apex.google_http.Connection')
    def test_no_redirect_or_error_body(self, connection, resolver):
        response = connection.return_value.getresponse.return_value
        response.status = 302
        self.assertEqual(fetch('profile', {}, 'test-token'), {'status':302})
        response.read.assert_not_called()
        connection.return_value.close.assert_called_once()

    @patch('apex.google_http.resolve_public', return_value=(2, '8.8.8.8'))
    @patch('apex.google_http.Connection')
    def test_json_response(self, connection, resolver):
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda key, default=None: {'Content-Type':'application/json'}.get(key, default)
        response.read.return_value = b'{"historyId":"1"}'
        self.assertEqual(fetch('profile', {}, 'test-token')['data'], {'historyId':'1'})
        response.read.return_value = b'[]'
        with self.assertRaises(ValueError): fetch('profile', {}, 'test-token')

    def test_token_header_injection_rejected_before_dns(self):
        with patch('apex.google_http.resolve_public') as resolver:
            with self.assertRaises(ValueError): fetch('profile', {}, 'token\r\nInjected: yes')
            resolver.assert_not_called()
