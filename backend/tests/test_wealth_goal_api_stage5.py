from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.wealth import router as wealth_router
from victor_ai_bot.runtime_services.wealth_goal_service import WealthGoalService
from victor_ai_bot.treasury.config import ProfitGoal


class _TreasuryCfg:
    def __init__(self):
        self.goal = ProfitGoal(target_return_percentage=8.0, time_horizon_seconds=14 * 86400, risk_tolerance='moderate', max_drawdown_pct=12.0, capital_commitment_pct=35.0)


class _Treasury:
    def __init__(self):
        self.cfg = _TreasuryCfg()

    def snapshot(self):
        return {'aggressiveness': {'current_return_pct': 4.5}}

    def _save_goal(self):
        return None


class _Runtime:
    def __init__(self, tmpdir: str):
        self._treasury = _Treasury()
        self._wealth_goal_service = WealthGoalService(data_dir=tmpdir, chain='ethereum')
        self._cc = None

    def drawdown_state(self):
        return {'drawdownPct': 1.25, 'hardStop': {'active': False}}

    def kill_switch_state(self):
        return {'suppressions': {}}

    def fund_summary_state(self):
        return {'fundStage': 'staging', 'riskPosture': 'balanced'}


def test_wealth_goal_endpoint_returns_canonical_state(tmp_path):
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _Runtime(str(tmp_path))
    client = TestClient(app)
    res = client.get('/api/wealth/goal')
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['state']['progressPct'] > 0
    assert 'explanation' in body
    assert 'history' in body
    assert body['recommendation']['target_return_pct'] >= 8.0


class _RuntimeNoTreasury:
    def __init__(self):
        self._treasury = None
        self._wealth_goal_service = None
        self._cc = None


def test_wealth_goal_endpoint_is_canonical_when_treasury_disabled() -> None:
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _RuntimeNoTreasury()
    client = TestClient(app)
    res = client.get('/api/wealth/goal')
    body = res.json()
    assert res.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'unavailable'
    assert body['reason_code'] == 'treasury_disabled'
    assert body['error'] == 'treasury_disabled'
    assert body['enabled'] is False
