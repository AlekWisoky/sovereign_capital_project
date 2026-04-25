from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.treasury_extra import router as treasury_router
from victor_ai_bot.runtime import RuntimeBundle


class _FakeGoal:
    def __init__(self):
        self.target_return_percentage = 12.5
        self.time_horizon_seconds = 3600
        self.risk_tolerance = "balanced"
        self.max_drawdown_pct = 8.0
        self.capital_commitment_pct = 25.0


class _FakeTreasury:
    def __init__(self):
        self.cfg = SimpleNamespace(goal=_FakeGoal())
        self.saved = 0

    def _save_goal(self):
        self.saved += 1


class _FakeRuntime:
    def __init__(self):
        self._treasury = _FakeTreasury()


def _client(runtime: _FakeRuntime) -> TestClient:
    app = FastAPI()
    app.include_router(treasury_router)
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    return TestClient(app)


def test_treasury_goal_update_is_atomic_on_invalid_numeric_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeRuntime()
    client = _client(runtime)

    response = client.post(
        "/api/treasury/goal",
        json={
            "target_return_percentage": 18.0,
            "capital_commitment_pct": {"bad": "shape"},
        },
        headers={"X-Admin-Key": "secret"},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["status"] == "invalid"
    assert body["error"] == "invalid_float_value"
    assert body["reason_code"] == "invalid_float_value"
    assert body["details"]["field"] == "capital_commitment_pct"
    assert runtime._treasury.saved == 0
    assert goal.target_return_percentage == 12.5
    assert goal.capital_commitment_pct == 25.0


def test_treasury_goal_update_rejects_unknown_fields_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeRuntime()
    client = _client(runtime)

    response = client.post(
        "/api/treasury/goal",
        json={"target_return_percentage": 18.0, "bogus": 1},
        headers={"X-Admin-Key": "secret"},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["status"] == "invalid"
    assert body["reason_code"] == "unknown_request_fields"
    assert body["details"]["fields"] == ["bogus"]
    assert runtime._treasury.saved == 0
    assert goal.target_return_percentage == 12.5


def test_treasury_goal_update_accepts_numeric_strings(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeRuntime()
    client = _client(runtime)

    response = client.post(
        "/api/treasury/goal",
        json={
            "target_return_percentage": "18.0",
            "time_horizon_seconds": "7200",
            "risk_tolerance": "strict",
            "max_drawdown_pct": "5.5",
            "capital_commitment_pct": "42.0",
        },
        headers={"X-Admin-Key": "secret"},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["goal"]["target_return_percentage"] == 18.0
    assert body["goal"]["time_horizon_seconds"] == 7200
    assert body["goal"]["risk_tolerance"] == "strict"
    assert body["goal"]["max_drawdown_pct"] == 5.5
    assert body["goal"]["capital_commitment_pct"] == 42.0
    assert runtime._treasury.saved == 1
    assert goal.target_return_percentage == 18.0
    assert goal.time_horizon_seconds == 7200


class _NoTreasuryRuntime:
    def __init__(self):
        self._treasury = None


class _NoCapitalRuntime:
    def __init__(self):
        self._treasury = _FakeTreasury()


def test_treasury_goal_and_capital_unavailable_payloads_are_canonical() -> None:
    app = FastAPI()
    app.include_router(treasury_router)
    app.state.runtime = _NoCapitalRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: _NoTreasuryRuntime()
    client = TestClient(app)

    capital = client.get('/api/treasury/capital').json()
    assert capital['ok'] is False
    assert capital['status'] == 'unavailable'
    assert capital['reason_code'] == 'capital_engine_state_unavailable'
    assert capital['error'] == 'capital_engine_state_unavailable'

    goal = client.get('/api/treasury/goal').json()
    assert goal['ok'] is False
    assert goal['status'] == 'unavailable'
    assert goal['reason_code'] == 'treasury_disabled'
    assert goal['error'] == 'treasury_disabled'
    assert goal['enabled'] is False


def test_treasury_goal_update_rejects_empty_payload_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeRuntime()
    client = _client(runtime)

    response = client.post(
        "/api/treasury/goal",
        json={},
        headers={"X-Admin-Key": "secret"},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["status"] == "invalid"
    assert body["reason_code"] == "empty_goal_patch"
    assert runtime._treasury.saved == 0
    assert goal.target_return_percentage == 12.5


def test_treasury_goal_noop_patch_skips_save(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeRuntime()
    client = _client(runtime)

    response = client.post(
        "/api/treasury/goal",
        json={"target_return_percentage": 12.5},
        headers={"X-Admin-Key": "secret"},
    )

    body = response.json()
    goal = runtime._treasury.cfg.goal
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["changed"] is False
    assert body["goal"]["target_return_percentage"] == 12.5
    assert runtime._treasury.saved == 0
    assert goal.target_return_percentage == 12.5
