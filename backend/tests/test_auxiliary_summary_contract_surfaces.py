from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.telemetry import (
    _execution_calibration_failed_payload,
    _telemetry_summary_failed_payload,
)
from victor_ai_bot.runtime_services.analytics_service import AnalyticsService
from victor_ai_bot.runtime_services.cio_service import CIOService
from victor_ai_bot.runtime_services.telemetry_service import TelemetryService
from victor_ai_bot.server import app
from victor_ai_bot.telemetry.store import TelemetryStore


class _TelemetryRuntime:
    def telemetry_summary(self):
        return {"ok": True, "realization": {"families": []}, "agents": {"agents": []}}

    def execution_calibration_state(self):
        return {"ok": True, "items": []}


class _CioRuntime:
    def fund_state(self):
        return {
            "capital": {"nav": 100.0},
            "risk": {"drawdown": 0.0},
            "alphaPlatform": {"enabled": True},
            "researchPipeline": {"throughput": {"researchHitRate": 1.0}},
            "internalPrime": {"borrowedUsd": 0.0},
        }


class _AnalyticsAux:
    def capital_truth(self, runtime):
        del runtime
        return SimpleNamespace(
            capital_summary={"navUsd": 10.0},
            capital_contract={"contractVersion": "capital_contract_v1", "status": "ok"},
            capital_policy={"contractVersion": "capital_policy_v1"},
        )

    def treasury_state(self, runtime, capital_truth=None):
        del runtime, capital_truth
        return {"ok": True, "enabled": True}


class _AnalyticsRuntime:
    def fund_summary_state(self):
        return {"health": {"status": "ok"}}

    def capital_truth_state(self):
        return {"ok": True, "status": "ok", "summaryContract": {"truthFamily": "capital_truth"}}

    def telemetry_summary(self):
        return {"ok": True, "summaryContract": {"truthFamily": "telemetry"}}

    def execution_calibration_state(self):
        return {"ok": True, "items": []}

    def agent_hub_state(self):
        return {"agents": []}

    def capital_engine_state(self):
        return {"capital_engine": {}}

    def endpoint_quality_state(self):
        return {"lanes": {}}

    def drawdown_state(self):
        return {"drawdownPct": 0.0}

    def kill_switch_state(self):
        return {"metrics": {}}

    def endpoint_universe_state(self):
        return {"read": {}}

    def venue_scorecards_state(self):
        return {"items": []}

    def route_quality_state(self):
        return {"items": []}

    def execution_live_state(self):
        return {"items": []}


def test_telemetry_service_and_routes_expose_summary_contracts(monkeypatch, tmp_path):
    store = TelemetryStore(data_dir=str(tmp_path), chain="ethereum")
    svc = TelemetryService(store=store)
    service_summary = svc.summary()
    service_health = svc.service_summary(_TelemetryRuntime())

    assert service_summary["summaryContract"]["truthFamily"] == "telemetry"
    assert service_summary["summaryContract"]["readModel"] == "telemetry_summary_projection_v1"
    assert service_health["summaryContract"]["truthFamily"] == "telemetry_service"

    monkeypatch.setattr(app.state, "runtime", _TelemetryRuntime(), raising=False)
    client = TestClient(app)
    summary = client.get("/api/telemetry/summary").json()
    calibration = client.get("/api/execution/calibration").json()

    assert summary["summaryContract"]["truthFamily"] == "telemetry"
    assert calibration["summaryContract"]["truthFamily"] == "execution_calibration"

    failed_summary = _telemetry_summary_failed_payload()
    failed_calibration = _execution_calibration_failed_payload()
    assert failed_summary["summaryContract"]["truthFamily"] == "telemetry"
    assert failed_calibration["summaryContract"]["truthFamily"] == "execution_calibration"


def test_cio_and_analytics_surfaces_expose_summary_contracts():
    cio = CIOService().summary(_CioRuntime())
    analytics = AnalyticsService(auxiliary_state=_AnalyticsAux()).system_summary(
        _AnalyticsRuntime()
    )

    assert cio["summaryContract"]["truthFamily"] == "cio"
    assert cio["summaryContract"]["readModel"] == "cio_summary_projection_v1"
    assert analytics["summaryContract"]["truthFamily"] == "analytics_system"
    assert analytics["summaryContract"]["readModel"] == "analytics_system_summary_projection_v1"
    assert analytics["summaryContract"]["capitalContractVersion"] == "capital_contract_v1"
