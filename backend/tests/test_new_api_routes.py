from fastapi.testclient import TestClient
from victor_ai_bot.server import app


def test_new_domain_routes_smoke():
    client = TestClient(app)
    for path in [
        '/api/agents/state',
        '/api/agents/attribution',
        '/api/treasury/capital',
        '/api/strategies/scorecards',
        '/api/evolution/state',
        '/api/telemetry/summary',
        '/api/execution/calibration',
    ]:
        r = client.get(path)
        assert r.status_code == 200
