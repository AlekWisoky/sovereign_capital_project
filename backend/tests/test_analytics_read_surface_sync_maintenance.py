from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _NoAnalyticsRuntime:
    pass


class _RouteAnalyticsRuntime:
    def quicksight_state(self):
        return {"ok": False, "status": "unavailable", "reason_code": "quicksight_unavailable", "reason": "quicksight_unavailable", "error": "quicksight_unavailable", "enabled": False}

    def quicksight_dataset(self, name: str):
        return {"ok": False, "status": "unavailable", "reason_code": "quicksight_unavailable", "reason": "quicksight_unavailable", "error": "quicksight_unavailable", "dataset": str(name), "rows": []}

    def quicksight_dashboards(self):
        return {"ok": False, "status": "unavailable", "reason_code": "quicksight_unavailable", "reason": "quicksight_unavailable", "error": "quicksight_unavailable", "dashboards": []}


def test_analytics_routes_fail_closed_when_runtime_lacks_quicksight_methods(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _NoAnalyticsRuntime(), raising=False)
    client = TestClient(app)

    state = client.get("/api/analytics/state").json()
    dataset = client.get("/api/analytics/datasets/operators").json()
    dashboards = client.get("/api/analytics/dashboards").json()

    assert state["ok"] is False
    assert state["status"] == "unavailable"
    assert state["reason_code"] == "quicksight_unavailable"
    assert state["error"] == "quicksight_unavailable"
    assert state["enabled"] is False

    assert dataset["ok"] is False
    assert dataset["status"] == "unavailable"
    assert dataset["reason_code"] == "quicksight_unavailable"
    assert dataset["dataset"] == "operators"
    assert dataset["rows"] == []

    assert dashboards["ok"] is False
    assert dashboards["status"] == "unavailable"
    assert dashboards["reason_code"] == "quicksight_unavailable"
    assert dashboards["dashboards"] == []


def test_analytics_routes_preserve_runtime_quicksight_unavailable_payloads(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _RouteAnalyticsRuntime(), raising=False)
    client = TestClient(app)

    state = client.get("/api/analytics/state").json()
    dataset = client.get("/api/analytics/datasets/exec").json()
    dashboards = client.get("/api/analytics/dashboards").json()

    assert state["reason_code"] == "quicksight_unavailable"
    assert state["ok"] is False
    assert dataset["dataset"] == "exec"
    assert dataset["reason_code"] == "quicksight_unavailable"
    assert dashboards["reason_code"] == "quicksight_unavailable"
