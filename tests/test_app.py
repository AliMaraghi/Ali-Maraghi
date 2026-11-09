from fastapi.testclient import TestClient
from apex.app import app

def test_status_is_honest():
    r=TestClient(app).get('/api/status')
    assert r.status_code==200
    data=r.json()
    assert data['llm_calls_enabled'] is False
    assert data['registered_production_agents']==0
    assert data['ai_budget_usd']==0

def test_pwa_exists():
    c=TestClient(app)
    assert c.get('/').status_code==200
    assert c.get('/manifest.webmanifest').json()['short_name']=='Apex'
