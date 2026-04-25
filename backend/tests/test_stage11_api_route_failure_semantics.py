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
    assert telemetry.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "telemetry_summary_failed",
        "reason": "telemetry_summary_failed",
        "error": "telemetry_summary_failed",
        "realization": {"families": []},
        "agents": {"agents": []},
        "auto_trade_recovery": {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "component": "",
            "history_status": "steady",
            "reliability_class": "stable",
            "reliability_reason_code": "ok",
            "reliability_reason_codes": [],
            "reliability_next_action": "",
            "component_reliability_class": "stable",
            "component_reliability_reason_code": "ok",
            "component_reliability_reason_codes": [],
            "component_reliability_next_action": "",
            "component_recovered_fragile": False,
            "recent_events": [],
        },
        "auto_trade_recovery_view": {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reasonCode": "ok",
            "reasonCodes": [],
            "suggestedNextAction": "",
            "component": "",
            "historyStatus": "steady",
            "degradedSinceTsMs": 0,
            "recoveredAtTsMs": 0,
            "degradedDurationMs": 0,
            "degradedCount": 0,
            "lastHealthyTsMs": 0,
            "recoveredRecently": False,
            "degradationSeverityClass": "stable",
            "historyComponent": "",
            "historyStage": "ok",
            "reliabilityClass": "stable",
            "reliabilityReasonCode": "ok",
            "reliabilityReasonCodes": [],
            "reliabilityNextAction": "",
            "componentReliabilityClass": "stable",
            "componentReliabilityReasonCode": "ok",
            "componentReliabilityReasonCodes": [],
            "componentReliabilityNextAction": "",
            "componentRecoveredFragile": False,
            "familyHardeningReasonCodes": [],
            "receiptOutcomeTruthReasonCodes": [],
        },
        "auto_trade_gate": {
            "allowed": True,
            "stage": "ok",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
        },
        "auto_trade_gate_view": {
            "allowed": True,
            "stage": "ok",
            "reasonCode": "ok",
            "reasonCodes": [],
            "suggestedNextAction": "",
        },
    }
    assert calibration.status_code == 200
    assert calibration.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "execution_calibration_failed",
        "reason": "execution_calibration_failed",
        "error": "execution_calibration_failed",
        "items": [],
        "auto_trade_recovery": {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "component": "",
            "history_status": "steady",
            "reliability_class": "stable",
            "reliability_reason_code": "ok",
            "reliability_reason_codes": [],
            "reliability_next_action": "",
            "component_reliability_class": "stable",
            "component_reliability_reason_code": "ok",
            "component_reliability_reason_codes": [],
            "component_reliability_next_action": "",
            "component_recovered_fragile": False,
            "recent_events": [],
        },
        "auto_trade_recovery_view": {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reasonCode": "ok",
            "reasonCodes": [],
            "suggestedNextAction": "",
            "component": "",
            "historyStatus": "steady",
            "degradedSinceTsMs": 0,
            "recoveredAtTsMs": 0,
            "degradedDurationMs": 0,
            "degradedCount": 0,
            "lastHealthyTsMs": 0,
            "recoveredRecently": False,
            "degradationSeverityClass": "stable",
            "historyComponent": "",
            "historyStage": "ok",
            "reliabilityClass": "stable",
            "reliabilityReasonCode": "ok",
            "reliabilityReasonCodes": [],
            "reliabilityNextAction": "",
            "componentReliabilityClass": "stable",
            "componentReliabilityReasonCode": "ok",
            "componentReliabilityReasonCodes": [],
            "componentReliabilityNextAction": "",
            "componentRecoveredFragile": False,
            "familyHardeningReasonCodes": [],
            "receiptOutcomeTruthReasonCodes": [],
        },
        "auto_trade_gate": {
            "allowed": True,
            "stage": "ok",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
        },
        "auto_trade_gate_view": {
            "allowed": True,
            "stage": "ok",
            "reasonCode": "ok",
            "reasonCodes": [],
            "suggestedNextAction": "",
        },
    }
    assert system_execution_quality.status_code == 200
    assert system_execution_quality.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "system_execution_quality_failed",
        "reason": "system_execution_quality_failed",
        "error": "system_execution_quality_failed",
        "calibration": {"items": []},
        "venue_profiles": {"venues": []},
        "risk_memory": {"failures": {}},
        "path_diversity": {"paths": []},
        "edge_learning": {"items": []},
        "endpoint_quality": {"lanes": {}, "summary": {}, "generatedAtMs": 0},
        "endpoint_universe": {"read": {}, "public": {}, "protected": {}, "private": {}},
        "venue_scorecards": {"pairs": {}},
        "route_quality": {"items": []},
        "live_execution": {"items": []},
        "drawdown": {},
        "kill_switch": {"suppressed": []},
        "auto_trade_recovery": {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "component": "",
            "history_status": "steady",
            "reliability_class": "stable",
            "reliability_reason_code": "ok",
            "reliability_reason_codes": [],
            "reliability_next_action": "",
            "component_reliability_class": "stable",
            "component_reliability_reason_code": "ok",
            "component_reliability_reason_codes": [],
            "component_reliability_next_action": "",
            "component_recovered_fragile": False,
        },
        "auto_trade_gate": {
            "allowed": True,
            "stage": "ok",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
        },
    }

    monkeypatch.setattr(app.state, "runtime", _RiskLiveStateRuntime(), raising=False)
    risk_live = client.get("/api/risk/live-state")
    assert risk_live.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "risk_live_state_failed",
        "reason": "risk_live_state_failed",
        "error": "risk_live_state_failed",
        "drawdown": {},
        "kill_switch": {"suppressed": []},
        "capital": {},
        "endpoint_quality": {},
        "endpoint_universe": {},
        "route_quality": {},
        "live_execution": {"items": []},
        "auto_trade_recovery": {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "component": "",
            "history_status": "steady",
            "reliability_class": "stable",
            "reliability_reason_code": "ok",
            "reliability_reason_codes": [],
            "reliability_next_action": "",
            "component_reliability_class": "stable",
            "component_reliability_reason_code": "ok",
            "component_reliability_reason_codes": [],
            "component_reliability_next_action": "",
            "component_recovered_fragile": False,
            "recent_events": [],
        },
        "auto_trade_gate": {
            "allowed": True,
            "stage": "ok",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
        },
    }

    monkeypatch.setattr(app.state, "runtime", _AgentRuntime(), raising=False)
    agent_state = client.get("/api/agents/state")
    attribution = client.get("/api/agents/attribution")
    assert agent_state.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "agent_hub_state_failed",
        "reason": "agent_hub_state_failed",
        "error": "agent_hub_state_failed",
        "state": {},
        "attribution": {"agents": []},
        "weights": {},
    }
    assert attribution.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "agent_attribution_failed",
        "reason": "agent_attribution_failed",
        "error": "agent_attribution_failed",
        "agents": [],
    }

    monkeypatch.setattr(app.state, "runtime", _StrategyRuntime(), raising=False)
    scorecards = client.get("/api/strategies/scorecards")
    assert scorecards.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "strategy_scorecards_failed",
        "reason": "strategy_scorecards_failed",
        "error": "strategy_scorecards_failed",
        "families": [],
    }

    monkeypatch.setattr(app.state, "runtime", _BrainRuntime(), raising=False)
    brain = client.get("/api/brain/state")
    assert brain.json() == {"ok": False, "error": "brain_unavailable"}

    monkeypatch.setattr(app.state, "runtime", _MetaRuntime(), raising=False)
    meta = client.get("/api/meta/candidates")
    assert meta.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "meta_candidates_failed",
        "reason": "meta_candidates_failed",
        "error": "meta_candidates_failed",
        "items": [],
        "candidates": [],
    }


def test_wealth_goal_update_tolerates_optional_audit_append_failures(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WealthRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/wealth/goal",
        headers={"X-Admin-Key": "secret"},
        json={"target_return_pct": 12.0, "reason": "raise_target"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["canonical"] is True
    assert body["service"] == "wealth_goal_service"
    assert body["goal"]["target_return_percentage"] == 12.0


class _MetaUnavailableRuntime:
    def meta_state(self):
        return {
            "ok": True,
            "enabled": False,
            "status": "unavailable",
            "reason_code": "meta_unavailable",
            "reason": "unavailable",
        }

    def meta_generate(self):
        return {
            "ok": False,
            "status": "unavailable",
            "reason_code": "meta_unavailable",
            "reason": "meta_unavailable",
            "error": "meta_unavailable",
            "candidates": [],
        }


def test_meta_candidate_route_does_not_report_success_when_meta_is_unavailable(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _MetaUnavailableRuntime(), raising=False)

    meta = client.get("/api/meta/candidates")
    assert meta.status_code == 200
    assert meta.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "meta_unavailable",
        "reason": "meta_unavailable",
        "error": "meta_unavailable",
        "items": [],
        "candidates": [],
    }


def test_system_summary_route_returns_deterministic_error_payload_when_projection_fails(
    monkeypatch,
):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _SystemSummaryRouteFailureRuntime(), raising=False)
    monkeypatch.setattr(
        "victor_ai_bot.api_routes.system_routes._service_health_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("service_health_failed")),
    )

    summary = client.get("/api/system/summary")
    assert summary.status_code == 200
    recovery = auto_trade_recovery_info(None)
    assert summary.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "system_summary_failed",
        "reason": "system_summary_failed",
        "error": "system_summary_failed",
        "services": unavailable_state("service_health_unavailable"),
        "capitalTruth": unavailable_state("capital_truth_unavailable"),
        "familyHardening": family_hardening_unavailable_summary(),
        "auto_trade_recovery": recovery,
        "auto_trade_gate": auto_trade_gate_info_from_recovery(recovery),
    }


def test_system_control_routes_return_deterministic_error_payloads(monkeypatch):
    from victor_ai_bot.api_routes import system_routes

    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _SystemControlRouteFailureRuntime(), raising=False)

    monkeypatch.setattr(
        system_routes,
        "_service_health_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("service health exploded")),
    )
    services = client.get("/api/system/services")

    monkeypatch.setattr(
        system_routes,
        "_capital_truth_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("capital truth exploded")),
    )
    capital_truth = client.get("/api/system/capital/truth")

    monkeypatch.setattr(
        system_routes,
        "_family_hardening_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("family hardening exploded")),
    )
    family_hardening = client.get("/api/system/family-hardening")

    monkeypatch.setattr(
        system_routes,
        "_capital_explain_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("capital explain exploded")),
    )
    capital_explain = client.get("/api/system/capital/explain")

    recovery = auto_trade_recovery_info(None)
    gate = auto_trade_gate_info_from_recovery(recovery)

    assert services.status_code == 200
    assert services.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "service_health_unavailable",
        "reason": "service_health_unavailable",
        "error": "system_services_failed",
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert capital_truth.status_code == 200
    assert capital_truth.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "capital_truth_unavailable",
        "reason": "capital_truth_unavailable",
        "error": "system_capital_truth_failed",
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert family_hardening.status_code == 200
    family_hardening_expected = family_hardening_unavailable_summary()
    family_hardening_expected["error"] = "system_family_hardening_failed"
    family_hardening_expected["auto_trade_recovery"] = recovery
    family_hardening_expected["auto_trade_gate"] = gate
    assert family_hardening.json() == family_hardening_expected

    assert capital_explain.status_code == 200
    assert capital_explain.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "capital_explanation_unavailable",
        "reason": "system_capital_explain_failed",
        "error": "system_capital_explain_failed",
        "text": "capital_explanation_unavailable",
        "facts": {},
        "causal": {},
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }
