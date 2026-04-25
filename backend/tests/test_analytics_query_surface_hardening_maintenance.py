from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _AnalyticsQueryRuntime:
    def __init__(self):
        self.calls = []

    def quicksight_ask(self, *, question: str, role: str, token: str):
        self.calls.append(("ask", question, role, token))
        return {"ok": True, "question": question, "role": role, "token": token}

    def quicksight_scenario(self, *, params: dict, role: str, token: str):
        self.calls.append(("scenario", dict(params or {}), role, token))
        return {"ok": True, "params": dict(params or {}), "role": role, "token": token}


def test_analytics_ask_rejects_empty_question_and_unknown_fields(monkeypatch):
    runtime = _AnalyticsQueryRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    empty = client.post("/api/analytics/ask", json={"question": "   "})
    unknown = client.post("/api/analytics/ask", json={"question": "status?", "extra": True})

    assert empty.json()["ok"] is False
    assert empty.json()["status"] == "invalid"
    assert empty.json()["reason_code"] == "empty_question"

    assert unknown.json()["ok"] is False
    assert unknown.json()["status"] == "invalid"
    assert unknown.json()["reason_code"] == "unknown_request_fields"
    assert runtime.calls == []


def test_analytics_query_routes_fail_closed_when_runtime_lacks_methods(monkeypatch):
    class _Runtime:
        pass

    monkeypatch.setattr(app.state, "runtime", _Runtime(), raising=False)
    client = TestClient(app)

    ask = client.post("/api/analytics/ask", json={"question": "status?"}).json()
    scenario = client.post("/api/analytics/scenario", json={"stress": "gas_5x"}).json()

    assert ask["ok"] is False
    assert ask["status"] == "unavailable"
    assert ask["reason_code"] == "quicksight_unavailable"
    assert ask["error"] == "quicksight_unavailable"

    assert scenario["ok"] is False
    assert scenario["status"] == "unavailable"
    assert scenario["reason_code"] == "quicksight_unavailable"
    assert scenario["error"] == "quicksight_unavailable"


def test_analytics_scenario_rejects_empty_payload_and_invalid_known_numeric_knobs(monkeypatch):
    runtime = _AnalyticsQueryRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    empty = client.post("/api/analytics/scenario", json={}).json()
    bad = client.post(
        "/api/analytics/scenario",
        json={"capital_shift": "bad", "stress": "gas_5x"},
    ).json()

    assert empty["ok"] is False
    assert empty["status"] == "invalid"
    assert empty["reason_code"] == "empty_scenario_params"

    assert bad["ok"] is False
    assert bad["status"] == "invalid"
    assert bad["reason_code"] == "invalid_float_value"
    assert bad["details"]["field"] == "capital_shift"
    assert runtime.calls == []


def test_analytics_scenario_preserves_generic_params_and_normalizes_known_numeric_knobs(monkeypatch):
    runtime = _AnalyticsQueryRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/analytics/scenario",
        json={"stress": "gas_5x", "capital_shift": "1.5"},
        headers={"X-Role": "RISK_MANAGER", "X-Role-Token": "tok-2"},
    ).json()

    assert response["ok"] is True
    assert response["params"]["stress"] == "gas_5x"
    assert response["params"]["capital_shift"] == 1.5
    assert runtime.calls == [("scenario", {"stress": "gas_5x", "capital_shift": 1.5}, "RISK_MANAGER", "tok-2")]
