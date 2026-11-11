import io
import unittest
from unittest.mock import Mock,patch
from pathlib import Path
from apex.console_server import ConsoleApp,ReloadingVerifier

class ConsoleServerTests(unittest.TestCase):
    def call(self,app,path='/api/status',token='valid',method='GET'):
        captured={}
        def start(status,headers):captured.update(status=status,headers=dict(headers))
        body=b''.join(app({'PATH_INFO':path,'REQUEST_METHOD':method,
                          'HTTP_CF_ACCESS_JWT_ASSERTION':token,'wsgi.input':io.BytesIO()},start))
        return captured,body
    def test_every_route_denies_before_data_or_assets(self):
        app=ConsoleApp(Path('.'),Mock(valid=Mock(return_value=False)))
        with patch('apex.console_server.content') as data:
            for path in ['/console','/reports','/api/status','/assets/console.js']:
                self.assertTrue(self.call(app,path)[0]['status'].startswith('401'))
            data.assert_not_called()
    def test_readonly_methods_csp_and_head(self):
        app=ConsoleApp(Path('.'),Mock(valid=Mock(return_value=True)))
        self.assertTrue(self.call(app,method='POST')[0]['status'].startswith('405'))
        with patch('apex.console_server.content',return_value=(b'{}','application/json')):
            response,body=self.call(app,method='HEAD')
        self.assertEqual(body,b'');self.assertEqual(response['headers']['Content-Length'],'2')
        self.assertNotIn('unsafe-inline',response['headers']['Content-Security-Policy'])
    def test_rate_limit_bounds_data_requests(self):
        app=ConsoleApp(Path('.'),Mock(valid=Mock(return_value=False)))
        with patch('apex.console_server.time.monotonic',return_value=1):
            for _ in range(300):self.call(app)
            response,_=self.call(app)
        self.assertTrue(response['status'].startswith('429'))
    def test_backend_errors_redacted(self):
        app=ConsoleApp(Path('.'),Mock(valid=Mock(return_value=True)))
        with patch('apex.console_server.content',side_effect=RuntimeError('PRIVATE')):
            response,body=self.call(app)
        self.assertTrue(response['status'].startswith('503'));self.assertNotIn(b'PRIVATE',body)
    def test_config_replacement_invalid_denies_old_valid_verifier(self):
        with patch.object(ReloadingVerifier,'_signature',return_value=(1,1,1)),patch('apex.console_server.AccessVerifier.load',return_value=Mock(valid=Mock(return_value=True))):
            verifier=ReloadingVerifier('/unused')
        with patch.object(verifier,'_signature',return_value=(1,2,1)),patch('apex.console_server.AccessVerifier.load',side_effect=ValueError):
            self.assertFalse(verifier.valid('old'))
