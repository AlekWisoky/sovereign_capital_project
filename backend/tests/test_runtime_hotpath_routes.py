from fastapi.testclient import TestClient

from victor_ai_bot.server import app


def test_runtime_routes_and_multichain_smoke(monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    deploy = client.get('/api/deploy/info')
    assert deploy.status_code == 200
    assert deploy.json()['brand']['name'] == 'x∆v'
    chains = client.get('/api/multichain/chains')
    assert chains.status_code == 200
    denied = client.post('/api/runtime/start')
    assert denied.status_code == 401
    allowed = client.post('/api/runtime/start', headers={'X-Admin-Key': 'secret'})
    assert allowed.status_code == 200
