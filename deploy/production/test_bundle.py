import unittest
import tempfile
from pathlib import Path
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

class AccessPolicyReviewTests(unittest.TestCase):
    def test_only_exact_owner_allowed(self):
        owner={'decision':'allow','include':[{'email':{'email':'owner@example.org'}}]}
        self.assertFalse(cloudflare_plan.validate_access_policies([owner],'owner@example.org')['live_policy_verified'])
        for policy in [{'decision':'bypass','include':[{'everyone':{}}]},
                       {'decision':'allow','include':[{'everyone':{}}]},
                       {'decision':'allow','include':[{'email':{'email':'other@example.org'}}]}]:
            with self.assertRaises(ValueError):cloudflare_plan.validate_access_policies([owner,policy],'owner@example.org')
    def test_non_uuid_tunnel_rejected(self):
        with self.assertRaises(ValueError):cloudflare_plan.plan('a'*32,'b'*32,'-'*36,'owner@example.org')

class InstallerSafetyTests(unittest.TestCase):
    def test_changed_unit_cannot_be_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'deploy/production').mkdir(parents=True)
            for name in install.UNITS:
                (root/'deploy/production'/name).write_bytes((install.ROOT/'deploy/production'/name).read_bytes())
            unit=root/'deploy/production'/install.UNITS[0]
            unit.write_bytes(unit.read_bytes().replace(b'User=apexdev',b'User=root'))
            with patch.object(install,'ROOT',root),patch.object(install,'DEST',root/'units'):
                with self.assertRaisesRegex(ValueError,'reviewed'):install.unit_payloads()

    def test_identical_reinstall_is_noop_conflict_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(install,'DEST',Path(tmp)):
            self.assertTrue(install.install_unit('apex.service',b'reviewed'))
            self.assertFalse(install.install_unit('apex.service',b'reviewed'))
            with self.assertRaises(ValueError):install.install_unit('apex.service',b'changed')
            self.assertEqual((Path(tmp)/'apex.service').read_bytes(),b'reviewed')

    def test_target_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(install,'DEST',Path(tmp)):
            target=Path(tmp)/'other';target.write_bytes(b'keep')
            (Path(tmp)/'apex.service').symlink_to(target)
            with self.assertRaises(ValueError):install.install_unit('apex.service',b'reviewed')
            self.assertEqual(target.read_bytes(),b'keep')

    def test_concurrent_different_unit_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(install,'DEST',Path(tmp)):
            def race(source,target):
                Path(target).write_bytes(b'another administrator')
                raise FileExistsError()
            with patch.object(install.os,'link',side_effect=race):
                with self.assertRaisesRegex(ValueError,'Concurrent'):install.install_unit('apex.service',b'reviewed')
            self.assertEqual((Path(tmp)/'apex.service').read_bytes(),b'another administrator')

    def test_root_requires_isolated_interpreter(self):
        with patch('sys.argv',['install.py','--apply']),patch.object(install,'check',return_value={}),patch.object(install.os,'geteuid',return_value=0),patch.object(install.sys,'flags') as flags,patch.object(install,'run') as run:
            flags.isolated=0
            with self.assertRaisesRegex(PermissionError,'python3 -I'):install.main()
            run.assert_not_called()

if __name__=='__main__':unittest.main()
