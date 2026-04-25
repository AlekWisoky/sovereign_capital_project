from fastapi.testclient import TestClient

from victor_ai_bot.server import create_app


def test_engine_state_route_exists():
    app = create_app()
    client = TestClient(app)
    res = client.get('/api/engines/state')
    assert res.status_code == 200
    body = res.json()
    assert 'items' in body
    assert 'capabilities' in body
