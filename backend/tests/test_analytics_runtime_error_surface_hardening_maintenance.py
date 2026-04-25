from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService


class _ExplodingQuickSight:
    def state(self):
        raise RuntimeError("state_boom")

    def get_dataset(self, name: str):
        del name
        raise RuntimeError("dataset_boom")

    def get_dashboards(self):
        raise RuntimeError("dashboards_boom")

    def ask(self, *, question: str, role: str, token: str):
        del question, role, token
        raise RuntimeError("ask_boom")

    def scenario(self, *, params, role: str, token: str):
        del params, role, token
        raise RuntimeError("scenario_boom")


class _ExplodingAnalyticsRuntime:
    def __init__(self):
        self._quicksight = _ExplodingQuickSight()
        self._auxiliary_state_service = AuxiliaryStateService()

    def quicksight_state(self):
        return self._auxiliary_state_service.quicksight_state(self)

    def quicksight_dataset(self, name: str):
        return self._auxiliary_state_service.quicksight_dataset(self, name)

    def quicksight_dashboards(self):
        return self._auxiliary_state_service.quicksight_dashboards(self)

    def quicksight_ask(self, *, question: str, role: str, token: str):
        return self._auxiliary_state_service.quicksight_ask(
            self,
            question=question,
            role=role,
            token=token,
        )

    def quicksight_scenario(self, *, params: dict, role: str, token: str):
        return self._auxiliary_state_service.quicksight_scenario(
            self,
            params=params,
            role=role,
            token=token,
        )


def _assert_degraded_read_payload(payload: dict, *, family: str, read_model: str, reason_code: str):
    summary_contract = payload.pop("summaryContract")
    assert payload["ok"] is False
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == reason_code
    assert payload["reason"] == reason_code
    assert payload["error"] == reason_code
    assert summary_contract == {
        "contractVersion": "canonical_summary_read_contract_v1",
        "truthFamily": family,
        "readModel": read_model,
        "capitalContractVersion": "",
        "capitalPolicyVersion": "",
        "sourceContracts": {},
        "ok": True,
        "synthesized": True,
        "stateContract": {
            "phase": f"{family}_summary",
            "status": "degraded",
            "reason_code": reason_code,
            "denied": False,
            "blocked": False,
            "degraded": True,
            "sticky_cycle": True,
            "details": {},
        },
    }


def test_analytics_routes_surface_deterministic_degraded_payloads_on_quicksight_failures(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _ExplodingAnalyticsRuntime(), raising=False)
    client = TestClient(app)

    state = client.get("/api/analytics/state").json()
    dataset = client.get("/api/analytics/datasets/operators").json()
    dashboards = client.get("/api/analytics/dashboards").json()
    ask = client.post("/api/analytics/ask", json={"question": "status?"}).json()
    scenario = client.post("/api/analytics/scenario", json={"stress": "gas_5x"}).json()

    _assert_degraded_read_payload(
        state,
        family="analytics_state",
        read_model="analytics_state_projection_v1",
        reason_code="quicksight_state_failed",
    )
    assert state["enabled"] is False

    _assert_degraded_read_payload(
        dataset,
        family="analytics_dataset",
        read_model="analytics_dataset_projection_v1",
        reason_code="quicksight_dataset_failed",
    )
    assert dataset["dataset"] == "operators"
    assert dataset["rows"] == []

    _assert_degraded_read_payload(
        dashboards,
        family="analytics_dashboards",
        read_model="analytics_dashboards_projection_v1",
        reason_code="quicksight_dashboards_failed",
    )
    assert dashboards["dashboards"] == []

    assert "summaryContract" not in ask
    assert ask == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_ask_failed",
        "reason": "quicksight_ask_failed",
        "error": "quicksight_ask_failed",
    }
    assert "summaryContract" not in scenario
    assert scenario == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_scenario_failed",
        "reason": "quicksight_scenario_failed",
        "error": "quicksight_scenario_failed",
    }
