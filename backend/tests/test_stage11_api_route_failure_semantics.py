from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.control_state import unavailable_state
from victor_ai_bot.runtime_services.family_hardening_service import (
    family_hardening_unavailable_summary,
)
from victor_ai_bot.runtime_services.state_service import (
    auto_trade_gate_info_from_recovery,
    auto_trade_recovery_info,
)
from victor_ai_bot.server import app


class _ExplodingAudit:
    def append(self, *args, **kwargs):
        raise ValueError("audit_sink_unavailable")


class _TelemetryRuntime:
    def telemetry_summary(self):
        raise RuntimeError("telemetry_not_ready")

    def execution_calibration_state(self):
        raise KeyError("calibration_missing")


class _AgentRuntime:
    def agent_hub_state(self):
        raise LookupError("agent_state_missing")

    def agent_attribution_state(self):
        raise RuntimeError("attribution_unavailable")


class _StrategyRuntime:
    def strategy_scorecards_state(self):
        raise RuntimeError("scorecards_unavailable")


class _BrainRuntime:
    def brain_state(self):
        raise RuntimeError("brain_not_ready")


class _MetaRuntime:
    def meta_state(self):
        raise RuntimeError("meta_state_failed")


class _RiskLiveStateRuntime:
    def drawdown_state(self):
        raise RuntimeError("drawdown_unavailable")


class _SystemSummaryRouteFailureRuntime:
    def __init__(self):
        self._analytics_service = SimpleNamespace(system_summary=lambda runtime: {"ok": True})


class _SystemControlRouteFailureRuntime:
    pass


class _WealthGoalService:
    def set_goal(self, runtime, payload, *, actor, reason):
        del runtime, payload, actor, reason
        return {"ok": True, "goal": {"target_return_percentage": 12.0}}


class _WealthRuntime:
    def __init__(self):
        self._treasury = object()
        self._wealth_goal_service = _WealthGoalService()
        self._cc = SimpleNamespace(audit=_ExplodingAudit())


def test_reporting_routes_return_deterministic_error_payloads(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _TelemetryRuntime(), raising=False)
    telemetry = client.get("/api/telemetry/summary")
    calibration = client.get("/api/execution/calibration")
    system_execution_quality = client.get("/api/system/execution/quality")
    assert telemetry.status_code == 200
    telemetry_body = telemetry.json()
    telemetry_core = dict(telemetry_body)
    telemetry_core.pop("summaryContract", None)
    assert telemetry_core["ok"] is False
    assert telemetry_core["reason_code"] == "telemetry_summary_failed"
    assert telemetry_body["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
    assert calibration.status_code == 200
    calibration_body = calibration.json()
    assert calibration_body["ok"] is False
    assert calibration_body["reason_code"] == "execution_calibration_failed"
    assert calibration_body["summaryContract"]["truthFamily"] == "execution_calibration"
    assert system_execution_quality.status_code == 200
    execution_body = system_execution_quality.json()
    assert execution_body["ok"] is False
    assert execution_body["reason_code"] == "system_execution_quality_failed"
    assert execution_body["auto_trade_gate"] == {"allowed": True,"stage": "ok","reason_code": "ok","reason_codes": [],"next_action": ""}

    monkeypatch.setattr(app.state, "runtime", _RiskLiveStateRuntime(), raising=False)
    risk_live = client.get("/api/risk/live-state")
    assert risk_live.json()["reason_code"] == "risk_live_state_failed"

    monkeypatch.setattr(app.state, "runtime", _AgentRuntime(), raising=False)
    assert client.get("/api/agents/state").json()["reason_code"] == "agent_hub_state_failed"
    assert client.get("/api/agents/attribution").json()["reason_code"] == "agent_attribution_failed"

    monkeypatch.setattr(app.state, "runtime", _StrategyRuntime(), raising=False)
    assert client.get("/api/strategies/scorecards").json()["reason_code"] == "strategy_scorecards_failed"

    monkeypatch.setattr(app.state, "runtime", _BrainRuntime(), raising=False)
    assert client.get("/api/brain/state").json() == {"ok": False, "error": "brain_unavailable"}

    monkeypatch.setattr(app.state, "runtime", _MetaRuntime(), raising=False)
    meta = client.get("/api/meta/candidates").json()
    assert meta["ok"] is False
    assert meta["reason_code"] == "meta_candidates_failed"
    assert meta["summaryContract"]["truthFamily"] == "meta_candidates"


def test_wealth_goal_update_tolerates_optional_audit_append_failures(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WealthRuntime(), raising=False)
    client = TestClient(app)
    resp = client.post("/api/wealth/goal", headers={"X-Admin-Key": "secret"}, json={"target_return_pct": 12.0, "reason": "raise_target"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["canonical"] is True
    assert body["service"] == "wealth_goal_service"
    assert body["goal"]["target_return_percentage"] == 12.0


class _MetaUnavailableRuntime:
    def meta_state(self):
        return {"ok": True,"enabled": False,"status": "unavailable","reason_code": "meta_unavailable","reason": "unavailable"}
    def meta_generate(self):
        return {"ok": False,"status": "unavailable","reason_code": "meta_unavailable","reason": "meta_unavailable","error": "meta_unavailable","candidates": []}


def test_meta_candidate_route_does_not_report_success_when_meta_is_unavailable(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _MetaUnavailableRuntime(), raising=False)
    meta = client.get("/api/meta/candidates").json()
    assert meta["ok"] is False
    assert meta["status"] == "unavailable"
    assert meta["reason_code"] == "meta_unavailable"
    assert meta["summaryContract"]["capitalContractVersion"] == "canonical_capital_summary_v1"


def test_system_summary_route_returns_deterministic_error_payload_when_projection_fails(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _SystemSummaryRouteFailureRuntime(), raising=False)
    monkeypatch.setattr("victor_ai_bot.api_routes.system_routes._service_health_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("service_health_failed")))
    summary = client.get("/api/system/summary")
    assert summary.status_code == 200
    assert summary.json()["reason_code"] == "system_summary_failed"


def test_system_control_routes_return_deterministic_error_payloads(monkeypatch):
    from victor_ai_bot.api_routes import system_routes
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _SystemControlRouteFailureRuntime(), raising=False)
    monkeypatch.setattr(system_routes, "_service_health_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("service health exploded")))
    services = client.get("/api/system/services")
    assert services.status_code == 200
    assert services.json()["reason_code"] == "service_health_unavailable"
