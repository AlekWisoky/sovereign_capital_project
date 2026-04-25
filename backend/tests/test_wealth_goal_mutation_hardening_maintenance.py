from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.wealth import router as wealth_router
from victor_ai_bot.runtime_services.wealth_goal_service import WealthGoalService
from victor_ai_bot.treasury.config import ProfitGoal


class _TreasuryCfg:
    def __init__(self):
        self.goal = ProfitGoal(
            target_return_percentage=11.0,
            time_horizon_seconds=7200,
            risk_tolerance='balanced',
            max_drawdown_pct=7.5,
            capital_commitment_pct=40.0,
        )


class _Treasury:
    def __init__(self):
        self.cfg = _TreasuryCfg()
        self.saved = 0

    def snapshot(self):
        return {'aggressiveness': {'current_return_pct': 4.5}}

    def _save_goal(self):
        self.saved += 1


class _Audit:
    def __init__(self):
        self.items = []

    def append(self, event, payload, **meta):
        self.items.append((event, payload, meta))


class _Runtime:
    def __init__(self, tmpdir: str):
        self._treasury = _Treasury()
        self._wealth_goal_service = WealthGoalService(data_dir=tmpdir, chain='ethereum')
        self._cc = SimpleNamespace(audit=_Audit())

    def drawdown_state(self):
        return {'drawdownPct': 1.25, 'hardStop': {'active': False}}

    def kill_switch_state(self):
        return {'suppressions': {}}

    def fund_summary_state(self):
        return {'fundStage': 'staging', 'riskPosture': 'balanced'}


def _client(tmp_path) -> tuple[TestClient, _Runtime]:
    runtime = _Runtime(str(tmp_path))
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = runtime
    return TestClient(app), runtime


def test_wealth_goal_partial_update_preserves_omitted_goal_fields(tmp_path, monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    client, runtime = _client(tmp_path)

    response = client.post(
        '/api/wealth/goal',
        headers={'X-Admin-Key': 'secret'},
        json={'target_return_pct': 15.0, 'reason': 'raise_target_only'},
    )

    body = response.json()
    goal = body['goal']
    assert response.status_code == 200
    assert body['ok'] is True
    assert goal['target_return_percentage'] == 15.0
    assert goal['time_horizon_seconds'] == 7200
    assert goal['risk_tolerance'] == 'balanced'
    assert goal['max_drawdown_pct'] == 7.5
    assert goal['capital_commitment_pct'] == 40.0
    assert runtime._treasury.saved == 1


def test_wealth_goal_update_rejects_unknown_fields_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    client, runtime = _client(tmp_path)

    response = client.post(
        '/api/wealth/goal',
        headers={'X-Admin-Key': 'secret'},
        json={'bogus': True},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'invalid'
    assert body['reason_code'] == 'unknown_request_fields'
    assert body['details']['fields'] == ['bogus']
    assert runtime._treasury.saved == 0
    assert goal.target_return_percentage == 11.0
    assert goal.time_horizon_seconds == 7200


def test_wealth_goal_update_rejects_invalid_horizon_before_service_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    client, runtime = _client(tmp_path)

    response = client.post(
        '/api/wealth/goal',
        headers={'X-Admin-Key': 'secret'},
        json={'time_horizon_seconds': 'not-an-int'},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'invalid'
    assert body['reason_code'] == 'invalid_integer_value'
    assert body['details']['field'] == 'time_horizon_seconds'
    assert runtime._treasury.saved == 0
    assert goal.time_horizon_seconds == 7200


def test_wealth_goal_update_rejects_reason_only_payload_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    client, runtime = _client(tmp_path)

    response = client.post(
        '/api/wealth/goal',
        headers={'X-Admin-Key': 'secret'},
        json={'reason': 'noop'},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'invalid'
    assert body['reason_code'] == 'empty_goal_patch'
    assert runtime._treasury.saved == 0
    assert runtime._cc.audit.items == []
    assert goal.target_return_percentage == 11.0


def test_wealth_goal_noop_patch_skips_save_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    client, runtime = _client(tmp_path)

    response = client.post(
        '/api/wealth/goal',
        headers={'X-Admin-Key': 'secret'},
        json={'target_return_pct': 11.0, 'reason': 'same_target'},
    )

    body = response.json()
    assert response.status_code == 200
    assert body['ok'] is True
    assert body['changed'] is False
    assert body['goal']['target_return_percentage'] == 11.0
    assert runtime._treasury.saved == 0
    assert runtime._cc.audit.items == []
