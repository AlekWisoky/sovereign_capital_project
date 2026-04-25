from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _FakeSuperstructureRuntime:
    def __init__(self):
        self.calls = []

    def superstructure_state(self):
        return {
            "ok": True,
            "enabled": True,
            "agents": [{"id": "agent-1", "status": "running"}],
            "stability": {"score": 0.97, "status": "steady"},
        }

    def superstructure_pause(self, agent_id: str):
        self.calls.append(("pause", agent_id))
        return agent_id == "agent-1"

    def superstructure_resume(self, agent_id: str):
        self.calls.append(("resume", agent_id))
        return agent_id == "agent-1"

    def governance_state(self):
        return {"ok": True, "enabled": True, "threat": {"level": "low"}}

    def governance_health(self):
        return {"ok": True, "score": 0.92, "status": "green"}


def test_superstructure_routes_use_canonical_module(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeSuperstructureRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    org = client.get("/api/org/state")
    stability = client.get("/api/org/stability")
    pause = client.post(
        "/api/org/agent/pause",
        json={"agent_id": "agent-1"},
        headers={"X-Admin-Key": "secret"},
    )
    resume = client.post(
        "/api/org/agent/resume",
        json={"agent_id": "agent-1"},
        headers={"X-Admin-Key": "secret"},
    )
    legacy_governance = client.get("/api/governance/state_legacy")
    governance_health = client.get("/api/governance/health")

    assert org.status_code == 200
    assert org.json()["agents"][0]["id"] == "agent-1"
    assert stability.json()["stability"]["status"] == "steady"
    assert pause.json()["ok"] is True
    assert resume.json()["ok"] is True
    assert legacy_governance.json()["threat"]["level"] == "low"
    assert governance_health.json()["status"] == "green"
    assert runtime.calls == [("pause", "agent-1"), ("resume", "agent-1")]


class _UnavailableSuperstructureRuntime:
    pass


def test_superstructure_route_unavailable_defaults_are_canonical_and_explicit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _UnavailableSuperstructureRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    org = client.get("/api/org/state").json()
    health = client.get("/api/governance/health").json()
    pause = client.post(
        "/api/org/agent/pause",
        json={"agent_id": "agent-1"},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert org["ok"] is False
    assert org["enabled"] is False
    assert org["reason"] == "unavailable"
    assert org["status"] == "unavailable"
    assert org["reason_code"] == "unavailable"
    assert org["auto_trade_recovery"]["blocked"] is False
    assert org["auto_trade_gate"]["allowed"] is True

    assert health["ok"] is False
    assert health["enabled"] is False
    assert health["reason"] == "unavailable"
    assert health["status"] == "unavailable"
    assert health["reason_code"] == "unavailable"
    assert health["auto_trade_recovery"]["blocked"] is False
    assert health["auto_trade_gate"]["allowed"] is True

    assert pause["ok"] is False
    assert pause["error"] == "unavailable"
    assert pause["status"] == "unavailable"
    assert pause["reason_code"] == "unavailable"


def test_superstructure_mutation_routes_require_explicit_agent_ids(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _FakeSuperstructureRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    pause_missing = client.post(
        "/api/org/agent/pause",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert pause_missing["ok"] is False
    assert pause_missing["status"] == "invalid"
    assert pause_missing["reason_code"] == "missing_agent_id"
    assert pause_missing["details"]["field"] == "agent_id"

    resume_blank = client.post(
        "/api/org/agent/resume",
        json={"agent_id": "   "},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert resume_blank["ok"] is False
    assert resume_blank["status"] == "invalid"
    assert resume_blank["reason_code"] == "invalid_string_value"
    assert resume_blank["details"]["field"] == "agent_id"

    pause_unknown = client.post(
        "/api/org/agent/pause",
        json={"agent_id": "agent-1", "reason": "policy"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert pause_unknown["ok"] is False
    assert pause_unknown["status"] == "invalid"
    assert pause_unknown["reason_code"] == "unknown_request_fields"
    assert pause_unknown["details"]["fields"] == ["reason"]

    assert runtime.calls == []
