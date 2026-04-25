from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.treasury_extra import router as treasury_router
from victor_ai_bot.api_routes.wealth import router as wealth_router
from victor_ai_bot.runtime import RuntimeBundle


class _Goal:
    def __init__(self):
        self.target_return_percentage = 8.0
        self.time_horizon_seconds = 14 * 86400
        self.risk_tolerance = "moderate"
        self.max_drawdown_pct = 12.0
        self.capital_commitment_pct = 35.0


class _TreasuryCfg:
    def __init__(self, goal):
        self.goal = goal


class _Treasury:
    def __init__(self, goal):
        self.cfg = _TreasuryCfg(goal)

    def snapshot(self):
        return {"aggressiveness": {"current_return_pct": 4.25}}


class _WealthRuntime:
    def __init__(self, goal):
        self._treasury = _Treasury(goal)
        self._wealth_goal_service = None
        self._cc = None


class _TreasuryRuntime:
    def __init__(self, goal, include_state: bool = False):
        self._treasury = _Treasury(goal)
        if include_state:
            self.treasury_state = lambda: {"ok": True, "allocator": "treasury"}


class _NoTreasuryStateRuntime:
    def __init__(self):
        self._treasury = _Treasury(_Goal())



def test_wealth_goal_fallback_read_surface_is_canonical():
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _WealthRuntime(_Goal())
    client = TestClient(app)

    response = client.get('/api/wealth/goal')
    body = response.json()

    assert response.status_code == 200
    assert body['ok'] is True
    assert body['status'] == 'available'
    assert body['canonical'] is True
    assert body['service'] == 'wealth_goal_fallback'
    assert body['goal']['goal_status'] == 'active'
    assert body['state']['targetReturnPct'] == 8.0
    assert body['state']['currentReturnPct'] == 4.25
    assert body['history'] == []
    assert 'why_posture' in body['explanation']
    assert body['recommendation']['target_return_pct'] >= 8.0



def test_wealth_goal_read_fails_closed_when_goal_missing():
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _WealthRuntime(goal=None)
    client = TestClient(app)

    response = client.get('/api/wealth/goal')
    body = response.json()

    assert response.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'unavailable'
    assert body['reason_code'] == 'treasury_goal_unavailable'
    assert body['goal'] is None
    assert body['state'] == {}
    assert body['history'] == []



def test_treasury_goal_read_surface_is_canonical():
    app = FastAPI()
    app.include_router(treasury_router)
    runtime = _TreasuryRuntime(_Goal(), include_state=True)
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    app.state.runtime = runtime
    client = TestClient(app)

    goal = client.get('/api/treasury/goal').json()
    state = client.get('/api/treasury/state').json()

    assert goal['ok'] is True
    assert goal['status'] == 'available'
    assert goal['canonical'] is True
    assert goal['service'] == 'treasury_goal_route'
    assert goal['goal']['target_return_pct'] == 8.0
    assert state['allocator'] == 'treasury'



def test_treasury_read_surfaces_fail_closed_when_state_or_goal_missing():
    app = FastAPI()
    app.include_router(treasury_router)
    runtime = _NoTreasuryStateRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    app.state.runtime = runtime
    client = TestClient(app)

    state = client.get('/api/treasury/state').json()
    assert state['ok'] is False
    assert state['status'] == 'unavailable'
    assert state['reason_code'] == 'treasury_state_unavailable'

    runtime._treasury.cfg.goal = None
    goal = client.get('/api/treasury/goal').json()
    assert goal['ok'] is False
    assert goal['status'] == 'unavailable'
    assert goal['reason_code'] == 'treasury_goal_unavailable'
    assert goal['goal'] is None
