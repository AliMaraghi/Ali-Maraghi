import unittest
from html.parser import HTMLParser
from pathlib import Path
from apex.kernel.console_ui import render, SECTIONS

class Tags(HTMLParser):
    def __init__(self):super().__init__();self.tags=[]
    def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))

class ConsoleTests(unittest.TestCase):
    def data(self):
        return {'providers':{'providers':[{'provider_id':'fts','connection_status':'VERIFIED_LIVE'}]},'reports':[{'trace_id':'actual-trace','ledger_seq':7,'status':'AWAITING_VALIDATION','unverified_candidates':2,'excluded':1,'sources':[]}], 'product':{'metrics':[{'label':'Verified receipts','value':1,'denominator':1,'source':'events','timestamp':None,'freshness':'HISTORICAL','confidence':'direct count','verification':'VERIFIED_OFFLINE'}],'roles':[{'id':'role','name':'<img src=x onerror=alert(1)>','status':'NOT_IMPLEMENTED'}],'timeline':[{'id':'event','title':'Untrusted </script><script>alert(1)</script>'}]}}
    def test_all_sections_and_evidence_are_server_rendered(self):
        html=render(self.data()).decode();tags=Tags();tags.feed(html)
        ids={attrs.get('id') for tag,attrs in tags.tags if tag=='section'}
        self.assertTrue({x[0] for x in SECTIONS}<=ids)
        self.assertIn('actual-trace',html);self.assertIn('HISTORICAL',html)
        self.assertIn('lang="fa"',html);self.assertIn('No records available',html)
    def test_untrusted_data_escaped_and_no_inline_handlers(self):
        html=render(self.data()).decode();tags=Tags();tags.feed(html)
        self.assertNotIn('<img src=x',html);self.assertNotIn('<script>alert',html)
        self.assertIn('&lt;img',html)
        for tag,attrs in tags.tags:
            self.assertFalse(any(k.lower().startswith('on') for k in attrs))
            if tag=='script':self.assertEqual(attrs.get('src'),'/assets/console.js')
            self.assertNotIn('style',attrs)
    def test_reports_route_initial_selection_and_export(self):
        html=render(self.data(),True).decode()
        self.assertIn('data-initial="reports"',html);self.assertIn('href="/reports.json"',html)
        self.assertIn('actual-trace',html)
    def test_assets_have_no_html_injection_sinks_or_remote_dependencies(self):
        root=Path(__file__).resolve().parents[1]/'core/apex/kernel/console_assets'
        js=(root/'console.js').read_text();css=(root/'console.css').read_text()
        for unsafe in ['innerHTML','eval(','document.write','fetch(','http://','https://']:
            self.assertNotIn(unsafe,js)
        self.assertIn('max-width:760px',css);self.assertIn('prefers-reduced-motion',css)
        self.assertIn('textContent',js);self.assertIn('root.dir',js)
