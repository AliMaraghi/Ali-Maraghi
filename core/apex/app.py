import os
from datetime import datetime, timezone
from html import escape
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from .storage import ensure_schema, list_items

app=FastAPI(title='Apex 4.4 private bootstrap',docs_url=None,redoc_url=None)

@app.get('/healthz')
def healthz():
    try:
        ensure_schema()
        return {"status":"ok","database":"connected"}
    except Exception:
        return JSONResponse(status_code=503,content={"status":"degraded","database":"unavailable"})

@app.get('/api/status')
def status():
    return {
        'name':'Apex 4.4', 'release':os.getenv('APEX_RELEASE','night1'),
        'mode':'private research bootstrap', 'llm_calls_enabled':False,
        'ai_budget_usd':0, 'registered_production_agents':0,
        'manifest_scope':'18 roles planned, not asserted implemented',
        'timestamp':datetime.now(timezone.utc).isoformat()
    }

@app.get('/api/observations')
def observations():
    try:
        records=list_items()
        return {'type':'public_rss_only','items':[
            {'source': r['source'], 'title':r['title'], 'url':r['url'], 'observed_at':r['observed_at'].isoformat()}
            for r in records]}
    except Exception:
        return JSONResponse(status_code=503,content={'error':'storage_unavailable','items':[]})

PAGE = """<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#101c29"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Apex">
<link rel="manifest" href="/manifest.webmanifest"><title>Apex — مرکز فرمان خصوصی</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:#101c29;color:#e9f1fa;margin:0;padding:22px;max-width:780px;margin:auto}h1{font-size:26px;letter-spacing:.4px}p{line-height:1.8} .card{background:#17283b;border:1px solid #29435b;border-radius:16px;padding:16px;margin:14px 0} .muted{color:#a3b5c6;font-size:13px}.tag{display:inline-block;border-radius:12px;background:#31557a;padding:6px 10px;font-size:12px}a{color:#b5d9ff}li{margin-bottom:16px}button{background:#3b78ad;color:white;border:0;border-radius:10px;padding:10px 16px}</style></head>
<body><h1>Apex 4.4</h1><p class="muted">مرکز فرمان خصوصی — نسخهٔ آزمایشی شب اول</p>
<div class="card"><strong>وضعیت زیرساخت</strong><p id="status">در حال بررسی…</p><span class="tag">هزینهٔ AI: صفر دلار</span></div>
<div class="card"><strong>رصد منابع عمومی علمی</strong><p class="muted">عنوان‌ها از RSS عمومی دریافت می‌شوند. این‌ها تحلیل هوش مصنوعی یا توصیهٔ شخصی نیستند.</p><ul id="items"><li>در حال دریافت…</li></ul></div>
<div class="card"><strong>آنچه هنوز ساخته نشده</strong><p>۱۸ عامل تخصصی، موتور سینمایی، یادگیری ماشین، اقدام خودکار مالی و اتصال حساب‌های شخصی هنوز در این نسخه فعال یا پیاده‌سازی نشده‌اند.</p></div>
<script>async function load(){try{const s=await (await fetch('/api/status')).json();document.getElementById('status').textContent='فعال — '+s.release+' — '+new Date().toLocaleString('fa-IR')}catch(e){document.getElementById('status').textContent='ارتباط برقرار نیست'}
try{const r=await (await fetch('/api/observations')).json();const ul=document.getElementById('items');ul.replaceChildren();if(!r.items.length){const li=document.createElement('li');li.textContent='هنوز موردی دریافت نشده یا منابع در دسترس نیستند.';ul.appendChild(li)}for(const x of r.items){const li=document.createElement('li');const a=document.createElement('a');a.textContent=x.title;a.href=x.url;a.rel='noopener noreferrer';a.target='_blank';const sm=document.createElement('small');sm.textContent=' — '+x.source;li.append(a,sm);ul.appendChild(li)}}catch(e){document.getElementById('items').textContent='دریافت داده ناموفق بود'}}load();setInterval(load,60000);</script></body></html>"""

@app.get('/',response_class=HTMLResponse)
def index():return PAGE

@app.get('/manifest.webmanifest')
def manifest():
    return JSONResponse({'name':'Apex Intelligence Core','short_name':'Apex','start_url':'/','display':'standalone','background_color':'#101c29','theme_color':'#101c29'})
