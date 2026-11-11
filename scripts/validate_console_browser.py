"""Local Waitress/browser test against real read-only ledger with ephemeral test JWT.
Not Cloudflare login, public deployment, or actual iPhone Safari acceptance.
"""
from pathlib import Path
import sys,threading,time,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'core'))
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from apex.kernel.access_auth import AccessVerifier
from apex.console_server import ConsoleApp
from waitress import create_server
from playwright.sync_api import sync_playwright
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk.update(kid='local-test',alg='RS256',use='sig')
now=int(time.time());issuer='https://test-only.cloudflareaccess.com'
verifier=AccessVerifier({'issuer':issuer,'audience':'a'*64,'owner_email':'test-owner@example.org',
 'retrieved_at':now-1,'expires_at':now+600,'source_url':issuer+'/cdn-cgi/access/certs','jwks':{'keys':[jwk]}})
token=jwt.encode({'iss':issuer,'aud':'a'*64,'email':'test-owner@example.org','sub':'test-owner','iat':now-1,'exp':now+600},key,algorithm='RS256',headers={'kid':'local-test'})
server=create_server(ConsoleApp(ROOT,verifier),host='127.0.0.1',port=0,threads=4)
thread=threading.Thread(target=server.run,daemon=True);thread.start()
base='http://127.0.0.1:'+str(server.effective_port)
result={'scope':'LOCAL_WAITRESS_REAL_LEDGER_TEST_IDENTITY_NOT_PUBLIC_DEPLOYMENT','checks':[]}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  context=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  for route in ['/console','/reports','/api/status','/assets/console.js']:
   res=page.goto(base+route);assert res.status==401;result['checks'].append({'route':route,'unauthorized':res.status})
  context.set_extra_http_headers({'Cf-Access-Jwt-Assertion':token})
  res=page.goto(base+'/console');assert res.status==200
  page.wait_for_selector('html.js-ready')
  assert page.locator('.panel').count()==12
  assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  page.screenshot(path=str(ROOT/'reports/validation/console_mobile.png'),full_page=True)
  page.locator('#language').click();assert page.locator('html').get_attribute('dir')=='rtl'
  page.locator('#theme').click();page.screenshot(path=str(ROOT/'reports/validation/console_persian.png'),full_page=True)
  for link in page.locator('[data-section]').all():
   target=link.get_attribute('data-section');page.goto(base+'/console#'+target)
   page.wait_for_selector('#'+target+'.active')
  page.goto(base+'/reports');page.wait_for_selector('#reports.active')
  response=context.request.get(base+'/api/status');assert response.status==200
  data=response.json();assert len(data['product']['roles'])==18
  result.update(panels=12,roles=18,audit_events=data['audit_events_verified'],product_commit=data['product']['commit'],browser_errors=errors,phone_viewport='390x844 Chromium, not actual Safari')
  assert not errors
  page.set_viewport_size({'width':1440,'height':1000});page.goto(base+'/console');page.screenshot(path=str(ROOT/'reports/validation/console_desktop.png'),full_page=True)
  browser.close()
finally:
 server.close()
(ROOT/'reports/validation/console_browser.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
