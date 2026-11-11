"""Bounded Google token exchange. Never logs request/response bodies or retries."""
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from .google_oauth_state import bounded
from .sources.public_http import Connection, resolve_public
from .kernel.schema import strict_json


def validate(form):
    if not isinstance(form, dict): raise ValueError('Invalid token form')
    grant = form.get('grant_type')
    required = {'client_id','client_secret','grant_type'}
    if grant == 'authorization_code': required |= {'code','code_verifier','redirect_uri'}
    elif grant == 'refresh_token': required |= {'refresh_token'}
    else: raise ValueError('Unsupported grant')
    if set(form) != required: raise ValueError('Unexpected token fields')
    for value in form.values(): bounded(value,1,4096)
    if grant == 'authorization_code':
        if form['redirect_uri'] not in {'https://console.apexcorelab.uk/auth/google/callback','https://auth.apexcorelab.uk/auth/google/callback'}:
            raise ValueError('Invalid redirect')
        import re
        if not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',form['code_verifier']): raise ValueError('Invalid PKCE')


def fetch(form):
    validate(form)
    host='oauth2.googleapis.com';family,address=resolve_public(host)
    connection=Connection(host,family,address)
    try:
        connection.request('POST','/token',urlencode(form).encode(),{
            'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json',
            'Accept-Encoding':'identity','Connection':'close'})
        response=connection.getresponse()
        if response.status!=200:return {'status':response.status}
        if response.getheader('Content-Encoding','identity')!='identity' or response.getheader('Content-Type','').split(';')[0]!='application/json':raise ValueError('Invalid token response')
        body=response.read(65537)
        if len(body)>65536:raise ValueError('Oversized token response')
        data=strict_json(body.decode())
        if not isinstance(data,dict):raise ValueError('Invalid token object')
        return {'status':200,'data':data}
    finally:connection.close()


def exchange(form):
    validate(form)
    try:
        result=subprocess.run([sys.executable,'-B','-m','apex.google_token_http'],
            input=json.dumps(form).encode(),capture_output=True,timeout=20,
            env={'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'LANG':'C.UTF-8'})
        if result.returncode or len(result.stdout)>131072:raise ValueError('Invalid transport')
        response=strict_json(result.stdout.decode())
        if response.get('status')!=200:raise ValueError('Token exchange rejected')
        return response['data']
    except Exception:raise PermissionError('GOOGLE_TOKEN_EXCHANGE_FAILED') from None


if __name__=='__main__':
    try:print(json.dumps(fetch(strict_json(sys.stdin.buffer.read(32769).decode())),allow_nan=False))
    except Exception:print('{"status":0}')
