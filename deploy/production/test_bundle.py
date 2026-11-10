import unittest
from unittest.mock import patch
import cloudflare_plan
import install

class BundleTests(unittest.TestCase):
    def test_cloudflare_owner_only_and_unpublished_sensitive_routes(self):
        p=cloudflare_plan.plan('a'*32,'b'*32,'12345678-1234-1234-1234-123456789abc','owner@example.org')
        self.assertEqual(p['access_policy']['include'],[{'email':{'email':'owner@example.org'}}])
        self.assertEqual(len(p['unpublished']),3)
        self.assertNotIn('config',p)  # Never replace whole remote ingress.
    def test_invalid_identifiers_rejected(self):
        with self.assertRaises(ValueError):cloudflare_plan.plan('missing','b'*32,'x','*')
    def test_apply_requires_host_admin_without_running_commands(self):
        with patch('sys.argv',['install.py','--apply']),patch.object(install,'check',return_value={}),patch.object(install.os,'geteuid',return_value=1000),patch.object(install,'run') as run:
            with self.assertRaises(PermissionError):install.main()
            run.assert_not_called()
    def test_default_does_not_run_host_commands(self):
        with patch('sys.argv',['install.py']),patch.object(install,'check',return_value={}),patch.object(install,'run') as run,patch('builtins.print'):
            install.main();run.assert_not_called()

if __name__=='__main__':unittest.main()
