from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.server import app


class _FakeThreat:
    def snapshot(self):
        return {"level": "low", "code": "green"}


class _FakeGov:
    def __init__(self):
        self.calls = []
        self.threat = _FakeThreat()

    def view_intent(self, *, intent_id: str):
        self.calls.append(("view", intent_id))
        return {"ok": True, "intent": {"id": intent_id}}

    def approve_intent(self, *, intent_id: str, reviewer: str):
        self.calls.append(("approve", intent_id, reviewer))
        return True

    def reject_intent(self, *, intent_id: str, reviewer: str):
        self.calls.append(("reject", intent_id, reviewer))
        return True


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
        self._gov = _FakeGov()
        self._treasury = _FakeTreasury()


def test_governance_and_treasury_routes_use_canonical_modules(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        intent = client.get("/api/governance/intent/intent-1")
        approve = client.post(
            "/api/governance/intent/intent-1/approve",
            headers={"X-Admin-Key": "secret"},
        )
        reject = client.post(
            "/api/governance/intent/intent-1/reject",
            headers={"X-Admin-Key": "secret"},
        )
        threat = client.get("/api/governance/threat_status")
        goal = client.get("/api/treasury/goal")
        set_goal = client.post(
            "/api/treasury/goal",
            json={
                "target_return_percentage": 18.0,
                "time_horizon_seconds": 7200,
                "risk_tolerance": "strict",
                "max_drawdown_pct": 5.5,
                "capital_commitment_pct": 42.0,
            },
            headers={"X-Admin-Key": "secret"},
        )

        assert intent.status_code == 200
        assert intent.json()["intent"]["id"] == "intent-1"
        assert approve.json()["ok"] is True
        assert approve.json()["approved"] is True
        assert approve.json()["intent_id"] == "intent-1"
        assert reject.json()["ok"] is True
        assert reject.json()["rejected"] is True
        assert reject.json()["intent_id"] == "intent-1"
        assert threat.json()["threat"]["code"] == "green"
        assert goal.json()["goal"]["risk_tolerance"] == "balanced"
        assert set_goal.json()["goal"]["target_return_percentage"] == 18.0
        assert runtime._treasury.cfg.goal.time_horizon_seconds == 7200
        assert runtime._treasury.saved == 1
        assert runtime._gov.calls == [
            ("view", "intent-1"),
            ("approve", "intent-1", "human"),
            ("reject", "intent-1", "human"),
        ]
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)


class _GovUnavailableRuntime:
    def __init__(self):
        self._gov = None


def test_governance_routes_expose_canonical_unavailable_semantics(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _GovUnavailableRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        intent = client.get("/api/governance/intent/intent-9")
        approve = client.post(
            "/api/governance/intent/intent-9/approve",
            headers={"X-Admin-Key": "secret"},
        )
        reject = client.post(
            "/api/governance/intent/intent-9/reject",
            headers={"X-Admin-Key": "secret"},
        )
        threat = client.get("/api/governance/threat_status")

        for payload in (intent.json(), approve.json(), reject.json(), threat.json()):
            assert payload["ok"] is False
            assert payload["status"] == "unavailable"
            assert payload["reason_code"] == "governance_disabled"
            assert payload["error"] == "governance_disabled"
            assert payload["enabled"] is False

        assert intent.json()["intent_id"] == "intent-9"
        assert approve.json()["intent_id"] == "intent-9"
        assert approve.json()["approved"] is False
        assert reject.json()["intent_id"] == "intent-9"
        assert reject.json()["rejected"] is False
        assert threat.json()["threat"] == {}
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)
