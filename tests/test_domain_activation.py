import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('domain_check',ROOT/'scripts/check_domain_activation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class DomainActivationTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'deploy/cloudflare'
        self.config=json.loads((folder/'activation.json').read_text())
        self.ingress=json.loads((folder/'remote-deny-all.json').read_text())

    def test_default_exposes_no_service(self):
        result=module.validate(self.config,self.ingress)
        self.assertEqual(result['working_urls'],[])
        self.assertEqual(result['zone_active'],'UNVERIFIED')

    def test_each_route_rejects_accidental_activation(self):
        for host in self.config['routes']:
            for value in [True,1,'false',None]:
                c=copy.deepcopy(self.config);c['routes'][host]['enabled']=value
                with self.assertRaises(ValueError):module.validate(c,self.ingress)

    def test_no_database_admin_or_callback_passthrough(self):
        for service in ['http://127.0.0.1:8080','tcp://localhost:5432','tcp://localhost:6379','http://localhost:5678']:
            c=copy.deepcopy(self.config);c['routes']['api.apexcorelab.uk']['upstream']=service
            with self.assertRaises(ValueError):module.validate(c,self.ingress)
            with self.assertRaises(ValueError):module.validate(self.config,{'config':{'ingress':[{'service':service}]}})

    def test_unknown_host_and_missing_guard_rejected(self):
        c=copy.deepcopy(self.config);c['routes']['admin.apexcorelab.uk']={}
        with self.assertRaises(ValueError):module.validate(c,self.ingress)
        with self.assertRaises(ValueError):module.validate(self.config,{'config':{'ingress':[]}})
