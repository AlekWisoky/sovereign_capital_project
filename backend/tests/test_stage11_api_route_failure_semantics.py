from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.control_state import unavailable_state
from victor_ai_bot.runtime_services.family_hardening_service import family_hardening_unavailable_summary
from victor_ai_bot.runtime_services.state_service import auto_trade_gate_info_from_recovery, auto_trade_recovery_info
from victor_ai_bot.server import app


class _ExplodingAudit:
    def append(self, *args, **kwargs): raise ValueError("audit_sink_unavailable")

class _TelemetryRuntime:
    def telemetry_summary(self): raise RuntimeError("telemetry_not_ready")
    def execution_calibration_state(self): raise KeyError("calibration_missing")

class _AgentRuntime:
    def agent_hub_state(self): raise LookupError("agent_state_missing")
    def agent_attribution_state(self): raise RuntimeError("attribution_unavailable")

class _StrategyRuntime:
    def strategy_scorecards_state(self): raise RuntimeError("scorecards_unavailable")

class _BrainRuntime:
    def brain_state(self): raise RuntimeError("brain_not_ready")

class _MetaRuntime:
    def meta_state(self): raise RuntimeError("meta_state_failed")

class _RiskLiveStateRuntime:
    def drawdown_state(self): raise RuntimeError("drawdown_unavailable")

class _SystemSummaryRouteFailureRuntime:
    def __init__(self): self._analytics_service = SimpleNamespace(system_summary=lambda runtime: {"ok": True})

class _SystemControlRouteFailureRuntime: pass

class _WealthGoalService:
    def set_goal(self, runtime, payload, *, actor, reason):
        del runtime, payload, actor, reason
        return {"ok": True, "goal": {"target_return_percentage": 12.0}}

class _WealthRuntime:
    def __init__(self):
        self._treasury = object(); self._wealth_goal_service = _WealthGoalService(); self._cc = SimpleNamespace(audit=_ExplodingAudit())


def test_reporting_routes_return_deterministic_error_payloads(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _TelemetryRuntime(), raising=False)
    telemetry = client.get("/api/telemetry/summary"); calibration = client.get("/api/execution/calibration"); system_execution_quality = client.get("/api/system/execution/quality")
    assert telemetry.status_code == 200
    telemetry_body = telemetry.json(); telemetry_core = dict(telemetry_body); telemetry_core.pop("summaryContract", None)
    assert telemetry_core["ok"] is False and telemetry_core["reason_code"] == "telemetry_summary_failed"
    assert telemetry_body["summaryContract"] == {"ok": True, "contractVersion": "canonical_summary_read_contract_v1", "truthFamily": "telemetry", "readModel": "telemetry_summary_projection_v1", "synthesized": True, "capitalContractVersion": "", "capitalPolicyVersion": "", "stateContract": {"phase": "telemetry_summary", "status": "degraded", "reason_code": "telemetry_summary_failed", "degraded": True, "blocked": False, "denied": False, "sticky_cycle": True, "details": {}}, "sourceContracts": {}}
    assert calibration.status_code == 200
    calibration_body = calibration.json(); calibration_core = dict(calibration_body); calibration_core.pop("summaryContract", None)
    assert calibration_core["ok"] is False and calibration_core["reason_code"] == "execution_calibration_failed"
    assert calibration_core["auto_trade_recovery"]["recent_events"] == []
    assert calibration_body["summaryContract"] == {"ok": True, "contractVersion": "canonical_summary_read_contract_v1", "truthFamily": "execution_calibration", "readModel": "execution_calibration_summary_projection_v1", "synthesized": True, "capitalContractVersion": "", "capitalPolicyVersion": "", "stateContract": {"phase": "execution_calibration_summary", "status": "degraded", "reason_code": "execution_calibration_failed", "degraded": True, "blocked": False, "denied": False, "sticky_cycle": True, "details": {}}, "sourceContracts": {}}
    assert system_execution_quality.status_code == 200
    system_body = system_execution_quality.json()
    assert system_body["ok"] is False and system_body["reason_code"] == "system_execution_quality_failed"
    assert system_body["calibration"] == {"items": []}
    assert system_body["auto_trade_recovery"]["recent_events"] == []

    monkeypatch.setattr(app.state, "runtime", _RiskLiveStateRuntime(), raising=False)
    risk_live = client.get("/api/risk/live-state"); risk_body = risk_live.json()
    assert risk_live.status_code == 200 and risk_body["ok"] is True
    assert risk_body["drawdown"] == {} and risk_body["kill_switch"] == {"suppressed": []}
    assert risk_body["capitalTruthHealth"]["reasonCode"] == "ok"
    assert risk_body["summaryContract"]["truthFamily"] == "risk_live_state"
    assert risk_body["summaryContract"]["readModel"] == "risk_live_state_projection_v1"

    monkeypatch.setattr(app.state, "runtime", _AgentRuntime(), raising=False)
    agent_state = client.get("/api/agents/state"); attribution = client.get("/api/agents/attribution")
    agent_body = agent_state.json(); agent_contract = agent_body.pop("summaryContract")
    assert agent_body["ok"] is False and agent_body["reason_code"] == "agent_hub_state_failed" and agent_contract["truthFamily"] == "agent_hub"
    attribution_body = attribution.json(); attribution_contract = attribution_body.pop("summaryContract")
    assert attribution_body["ok"] is False and attribution_body["reason_code"] == "agent_attribution_failed" and attribution_contract["truthFamily"] == "agent_attribution"

    monkeypatch.setattr(app.state, "runtime", _StrategyRuntime(), raising=False)
    scorecards = client.get("/api/strategies/scorecards"); score_body = scorecards.json(); score_contract = score_body.pop("summaryContract")
    assert score_body["ok"] is False and score_body["reason_code"] == "strategy_scorecards_failed" and score_contract["truthFamily"] == "strategy_scorecards"

    monkeypatch.setattr(app.state, "runtime", _BrainRuntime(), raising=False)
    brain = client.get("/api/brain/state"); brain_body = brain.json(); brain_contract = brain_body.pop("summaryContract")
    assert brain_body == {"ok": False, "error": "brain_unavailable"}
    assert brain_contract == {"ok": True, "contractVersion": "canonical_summary_read_contract_v1", "truthFamily": "brain_state", "readModel": "brain_state_projection_v1", "synthesized": True, "capitalContractVersion": "canonical_capital_summary_v1", "capitalPolicyVersion": "capital_policy_v1", "stateContract": {"phase": "brain_state_summary", "status": "degraded", "reason_code": "brain_unavailable", "degraded": True, "blocked": False, "denied": False, "sticky_cycle": True, "details": {}}, "sourceContracts": {}}

    monkeypatch.setattr(app.state, "runtime", _MetaRuntime(), raising=False)
    meta = client.get("/api/meta/candidates"); meta_body = meta.json(); meta_core = dict(meta_body); meta_core.pop("summaryContract", None)
    assert meta_core["ok"] is False and meta_core["reason_code"] == "meta_candidates_failed"
    assert meta_body["summaryContract"]["truthFamily"] == "meta_candidates"


def test_wealth_goal_update_tolerates_optional_audit_append_failures(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret"); monkeypatch.setattr(app.state, "runtime", _WealthRuntime(), raising=False)
    resp = TestClient(app).post("/api/wealth/goal", headers={"X-Admin-Key": "secret"}, json={"target_return_pct": 12.0, "reason": "raise_target"})
    assert resp.status_code == 200
    body = resp.json(); assert body["ok"] is True; assert body["canonical"] is True; assert body["service"] == "wealth_goal_service"; assert body["goal"]["target_return_percentage"] == 12.0

class _MetaUnavailableRuntime:
    def meta_state(self): return {"ok": True, "enabled": False, "status": "unavailable", "reason_code": "meta_unavailable", "reason": "unavailable"}
    def meta_generate(self): return {"ok": False, "status": "unavailable", "reason_code": "meta_unavailable", "reason": "meta_unavailable", "error": "meta_unavailable", "candidates": []}

def test_meta_candidate_route_does_not_report_success_when_meta_is_unavailable(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _MetaUnavailableRuntime(), raising=False)
    meta = TestClient(app).get("/api/meta/candidates"); assert meta.status_code == 200
    body = meta.json(); core = dict(body); core.pop("summaryContract", None)
    assert core == {"ok": False, "status": "unavailable", "reason_code": "meta_unavailable", "reason": "meta_unavailable", "error": "meta_unavailable", "items": [], "candidates": []}
    assert body["summaryContract"]["truthFamily"] == "meta_candidates"

def test_system_summary_route_returns_deterministic_error_payload_when_projection_fails(monkeypatch):
    client = TestClient(app); monkeypatch.setattr(app.state, "runtime", _SystemSummaryRouteFailureRuntime(), raising=False)
    monkeypatch.setattr("victor_ai_bot.api_routes.system_routes._service_health_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("service_health_failed")))
    summary = client.get("/api/system/summary"); assert summary.status_code == 200; recovery = auto_trade_recovery_info(None)
    assert summary.json() == {"ok": False, "status": "degraded", "reason_code": "system_summary_failed", "reason": "system_summary_failed", "error": "system_summary_failed", "services": unavailable_state("service_health_unavailable"), "capitalTruth": unavailable_state("capital_truth_unavailable"), "familyHardening": family_hardening_unavailable_summary(), "auto_trade_recovery": recovery, "auto_trade_gate": auto_trade_gate_info_from_recovery(recovery)}

def test_system_control_routes_return_deterministic_error_payloads(monkeypatch):
    from victor_ai_bot.api_routes import system_routes
    client = TestClient(app); monkeypatch.setattr(app.state, "runtime", _SystemControlRouteFailureRuntime(), raising=False)
    monkeypatch.setattr(system_routes, "_service_health_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("service health exploded"))); services = client.get("/api/system/services")
    monkeypatch.setattr(system_routes, "_capital_truth_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("capital truth exploded"))); capital_truth = client.get("/api/system/capital/truth")
    monkeypatch.setattr(system_routes, "_family_hardening_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("family hardening exploded"))); family_hardening = client.get("/api/system/family-hardening")
    monkeypatch.setattr(system_routes, "_capital_explain_payload", lambda rt: (_ for _ in ()).throw(RuntimeError("capital explain exploded"))); capital_explain = client.get("/api/system/capital/explain")
    recovery = auto_trade_recovery_info(None); gate = auto_trade_gate_info_from_recovery(recovery)
    assert services.status_code == 200 and services.json() == {"ok": False, "status": "unavailable", "reason_code": "service_health_unavailable", "reason": "service_health_unavailable", "error": "system_services_failed", "auto_trade_recovery": recovery, "auto_trade_gate": gate}
    assert capital_truth.status_code == 200 and capital_truth.json() == {"ok": False, "status": "unavailable", "reason_code": "capital_truth_unavailable", "reason": "capital_truth_unavailable", "error": "system_capital_truth_failed", "auto_trade_recovery": recovery, "auto_trade_gate": gate}
    assert family_hardening.status_code == 200
    expected = family_hardening_unavailable_summary(); expected["error"] = "system_family_hardening_failed"; expected["auto_trade_recovery"] = recovery; expected["auto_trade_gate"] = gate
    assert family_hardening.json() == expected
    assert capital_explain.status_code == 200 and capital_explain.json() == {"ok": False, "status": "unavailable", "reason_code": "capital_explanation_unavailable", "reason": "system_capital_explain_failed", "error": "system_capital_explain_failed", "text": "capital_explanation_unavailable", "facts": {}, "causal": {}, "auto_trade_recovery": recovery, "auto_trade_gate": gate}
