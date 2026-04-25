from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.auto_trade_recovery_repository import (
    AutoTradeRecoveryRepository,
)


class _ExplodingTelemetryRuntime:
    def telemetry_summary(self):
        raise RuntimeError("telemetry_not_ready")

    def execution_calibration_state(self):
        raise ValueError("bad_calibration_snapshot")


def test_telemetry_routes_surface_canonical_degraded_payloads(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _ExplodingTelemetryRuntime(), raising=False)

    summary = client.get("/api/telemetry/summary")
    calibration = client.get("/api/execution/calibration")

    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["summaryContract"]["truthFamily"] == "telemetry"
    assert summary_body["summaryContract"]["readModel"] == "telemetry_summary_projection_v1"
    summary_body.pop("summaryContract")
    assert summary_body == {
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
    calibration_body = calibration.json()
    assert calibration_body["summaryContract"]["truthFamily"] == "execution_calibration"
    assert (
        calibration_body["summaryContract"]["readModel"]
        == "execution_calibration_summary_projection_v1"
    )
    calibration_body.pop("summaryContract")
    assert calibration_body == {
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


class _RecoveryTelemetryRuntime:
    def __init__(self, db_path: str):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
        self._db = PersistenceDB(db_path)
        self._repo = AutoTradeRecoveryRepository(self._db, chain="ethereum")

    def telemetry_summary(self):
        return {
            "ok": True,
            "realization": {"families": [{"family": "flashloan_atomic", "count": 1}]},
            "agents": {"agents": [{"name": "brain", "weight": 1.0}]},
        }

    def execution_calibration_state(self):
        return {"items": []}

    def seed_blocked(self):
        self._repo.observe(
            component="auto_trade_admission",
            degraded=True,
            ts_ms=1000,
            reason_code="capital_truth_degraded",
            stage="fund_hold",
            blocker_component="fund_health",
            next_action="restore_capital_truth",
            reason_codes=["capital_truth_degraded"],
        )
        self._repo.observe(
            component="auto_trade_admission",
            degraded=False,
            ts_ms=2000,
            reason_code="ok",
            stage="ok",
            blocker_component="",
            next_action="",
            reason_codes=[],
        )


def test_telemetry_summary_route_exports_auto_trade_gate_and_recovery_contract(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime.seed_blocked()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["realization"]["families"][0]["family"] == "flashloan_atomic"
    assert payload["agents"]["agents"][0]["name"] == "brain"
    assert payload["auto_trade_recovery"]["history_status"] == "recovered"
    assert payload["auto_trade_recovery_view"]["historyStatus"] == "recovered"
    assert payload["auto_trade_gate"] == {
        "allowed": True,
        "stage": "ok",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
    }
    assert payload["auto_trade_gate_view"] == {
        "allowed": True,
        "stage": "ok",
        "reasonCode": "ok",
        "reasonCodes": [],
        "suggestedNextAction": "",
    }


def test_execution_calibration_route_exports_auto_trade_gate_and_recovery_contract(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime.seed_blocked()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/execution/calibration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["auto_trade_recovery"]["history_status"] == "recovered"
    assert payload["auto_trade_recovery_view"]["historyStatus"] == "recovered"
    assert payload["auto_trade_gate"] == {
        "allowed": True,
        "stage": "ok",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
    }
    assert payload["auto_trade_gate_view"] == {
        "allowed": True,
        "stage": "ok",
        "reasonCode": "ok",
        "reasonCodes": [],
        "suggestedNextAction": "",
    }


def test_auto_trade_recovery_telemetry_route_exports_canonical_snapshot_and_events(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime.seed_blocked()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["component"] == "auto_trade_admission"
    assert payload["event_count"] == 2
    assert [evt["event_type"] for evt in payload["events"][:2]] == ["recovered", "blocked"]
    assert payload["history"] == payload["events"]
    assert [evt["eventType"] for evt in payload["history_items"][:2]] == ["recovered", "blocked"]
    assert payload["recovery"]["blocked"] is False
    assert payload["recovery_view"]["blocked"] is False
    assert payload["recovery"]["ready"] is True
    assert payload["recovery"]["history_status"] == "recovered"
    assert payload["recovery"]["recovered_at_ts_ms"] == 2000
    assert payload["recovery"]["reason_code"] == "ok"
    assert payload["recovery_view"]["historyStatus"] == "recovered"
    assert payload["recovery_view"]["recoveredAtTsMs"] == 2000
    assert payload["recovery_view"]["reasonCode"] == "ok"
    assert payload["auto_trade_gate"] == {
        "allowed": True,
        "stage": "ok",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
    }
    assert payload["auto_trade_gate_view"] == {
        "allowed": True,
        "stage": "ok",
        "reasonCode": "ok",
        "reasonCodes": [],
        "suggestedNextAction": "",
    }


def test_auto_trade_recovery_telemetry_route_preserves_receipt_outcome_truth_history_details(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "degraded",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="receipt_outcome_truth",
        next_action="",
        reason_codes=[],
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery"]["history_component"] == "receipt_outcome_truth"
    assert payload["recovery"]["receipt_outcome_truth_reason_codes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert payload["recovery_view"]["historyComponent"] == "receipt_outcome_truth"
    assert payload["recovery_view"]["receiptOutcomeTruthReasonCodes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert payload["recovery_view"]["componentReliabilityClass"] == "degraded"
    assert payload["recovery_view"]["componentReliabilityReasonCode"] == (
        "receipt_outcome_truth_reliability_degraded"
    )
    assert payload["recovery_view"]["componentReliabilityReasonCodes"] == [
        "receipt_outcome_truth_reliability_degraded",
        "settled_profit_truth_unavailable",
    ]
    assert payload["recovery_view"]["componentReliabilityNextAction"] == (
        "restore_receipt_outcome_truth"
    )
    assert payload["history_items"][0]["historyComponent"] == "receipt_outcome_truth"
    assert payload["history_items"][0]["receiptOutcomeTruthReasonCodes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert payload["history_items"][0]["componentReliabilityClass"] == "degraded"
    assert payload["history_items"][0]["componentReliabilityReasonCode"] == (
        "receipt_outcome_truth_reliability_degraded"
    )
    assert payload["history_items"][0]["reliabilityReasonCode"] == (
        "receipt_outcome_truth_reliability_degraded"
    )
    assert payload["history_items"][1]["receiptOutcomeTruthReasonCodes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert payload["history_items"][1]["componentReliabilityClass"] == "degraded"


def test_auto_trade_recovery_telemetry_route_surfaces_canonical_degraded_payload(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", object(), raising=False)
    monkeypatch.setattr(
        "victor_ai_bot.api_routes._route_helpers.current_auto_trade_recovery_info",
        lambda rt: (_ for _ in ()).throw(RuntimeError("recovery_store_failed")),
    )

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["summaryContract"]["truthFamily"] == "auto_trade_recovery"
    assert (
        response_body["summaryContract"]["readModel"] == "auto_trade_recovery_summary_projection_v1"
    )
    response_body.pop("summaryContract")
    assert response_body == {
        "ok": False,
        "status": "degraded",
        "reason_code": "auto_trade_recovery_failed",
        "reason": "auto_trade_recovery_failed",
        "error": "auto_trade_recovery_failed",
        "component": "auto_trade_admission",
        "recovery": {
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
        "recovery_view": {
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
        "events": [],
        "history": [],
        "history_items": [],
        "event_count": 0,
    }


def test_auto_trade_recovery_telemetry_route_surfaces_component_recovered_fragile(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="receipt_outcome_truth",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery_view"]["componentRecoveredFragile"] is True
    assert payload["history_items"][0]["componentRecoveredFragile"] is True


def test_auto_trade_recovery_repository_reasserts_canonical_component_context_after_payload_overrides(
    tmp_path,
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "degraded",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="receipt_outcome_truth",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "bogus_component",
            "history_stage": "bogus_stage",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "family_hardening_reason_codes": [0, "", "family_hardening_rebuild_required", 0],
            "receipt_outcome_truth_reason_codes": [
                "",
                "settled_profit_truth_unavailable",
                0,
                "settled_profit_truth_unavailable",
            ],
        },
    )

    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["history_component"] == "receipt_outcome_truth"
    assert persisted["history_stage"] == "fund_hold"
    assert persisted["family_hardening_reason_codes"] == [
        "0",
        "family_hardening_rebuild_required",
        "0",
    ]
    assert persisted["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]

    events = runtime._repo.recent_events(component="auto_trade_admission", limit=2)
    assert events[0]["history_component"] == "receipt_outcome_truth"
    assert events[0]["history_stage"] == "fund_hold"
    assert events[0]["family_hardening_reason_codes"] == [
        "0",
        "family_hardening_rebuild_required",
        "0",
    ]
    assert events[0]["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]


def test_auto_trade_recovery_repository_carries_component_fragility_across_recovery_without_manual_flag(
    tmp_path,
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "degraded",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "component_recovered_fragile": False,
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="receipt_outcome_truth",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "component_recovered_fragile": False,
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )

    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["component_recovered_fragile"] is True

    events = runtime._repo.recent_events(component="auto_trade_admission", limit=2)
    assert events[0]["event_type"] == "recovered"
    assert events[0]["component_recovered_fragile"] is True


def test_auto_trade_recovery_telemetry_route_uses_history_component_and_component_next_action_for_recovered_events(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "",
            "history_stage": "ok",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["history_items"][0]["eventType"] == "recovered"
    assert payload["history_items"][0]["component"] == "receipt_outcome_truth"
    assert payload["history_items"][0]["historyComponent"] == "receipt_outcome_truth"
    assert payload["history_items"][0]["suggestedNextAction"] == ("restore_receipt_outcome_truth")


def test_auto_trade_recovery_telemetry_route_uses_history_stage_and_reason_for_recovered_events(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "",
            "history_stage": "ok",
            "history_reason_code": "ok",
            "history_reason_codes": [],
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["history_items"][0]["eventType"] == "recovered"
    assert payload["history_items"][0]["stage"] == "fund_hold"
    assert payload["history_items"][0]["reasonCode"] == "settled_profit_truth_unavailable"
    assert payload["history_items"][0]["reasonCodes"] == ["settled_profit_truth_unavailable"]


def test_auto_trade_recovery_telemetry_route_uses_history_component_and_component_next_action_for_recovered_current_view(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_status": "blocked",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "",
            "history_stage": "ok",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery_view"]["component"] == "receipt_outcome_truth"
    assert payload["recovery_view"]["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_telemetry_route_uses_history_stage_and_reason_for_recovered_current_view(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_status": "blocked",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="ok",
        stage="ok",
        blocker_component="",
        next_action="",
        reason_codes=[],
        payload_extras={
            "history_component": "",
            "history_stage": "ok",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery_view"]["stage"] == "fund_hold"
    assert payload["recovery_view"]["reasonCode"] == "settled_profit_truth_unavailable"
    assert payload["recovery_view"]["reasonCodes"] == ["settled_profit_truth_unavailable"]


def test_auto_trade_recovery_repository_ignores_stale_live_override_args_on_recovery(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_reason_code": "settled_profit_truth_unavailable",
            "history_reason_codes": ["settled_profit_truth_unavailable"],
            "history_status": "blocked",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_reason_code": "settled_profit_truth_unavailable",
            "history_reason_codes": ["settled_profit_truth_unavailable"],
            "history_next_action": "restore_receipt_outcome_truth",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["last_stage"] == "ok"
    assert persisted["last_reason_code"] == "ok"
    assert persisted["last_reason_codes"] == []
    assert persisted["last_blocker_component"] == ""
    assert persisted["last_next_action"] == ""

    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)
    response = client.get("/api/telemetry/auto-trade-recovery")
    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery_view"]["stage"] == "fund_hold"
    assert payload["recovery_view"]["reasonCode"] == "settled_profit_truth_unavailable"
    assert payload["recovery_view"]["component"] == "receipt_outcome_truth"
    assert payload["recovery_view"]["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_repository_clears_current_last_fields_on_recovery_without_live_overrides(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_reason_code": "settled_profit_truth_unavailable",
            "history_reason_codes": ["settled_profit_truth_unavailable"],
            "history_status": "blocked",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        payload_extras={
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_reason_code": "settled_profit_truth_unavailable",
            "history_reason_codes": ["settled_profit_truth_unavailable"],
            "history_next_action": "restore_receipt_outcome_truth",
            "history_status": "recovered",
            "reliability_class": "fragile",
            "reliability_reason_code": "auto_trade_recovery_fragile",
            "reliability_reason_codes": ["auto_trade_recovery_fragile"],
            "reliability_next_action": "monitor_auto_trade_reentry",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["last_stage"] == "ok"
    assert persisted["last_reason_code"] == "ok"
    assert persisted["last_blocker_component"] == ""
    assert persisted["last_next_action"] == ""
    assert persisted["last_reason_codes"] == []
    assert persisted["history_stage"] == "fund_hold"
    assert persisted["history_reason_code"] == "settled_profit_truth_unavailable"

    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery_view"]["stage"] == "fund_hold"
    assert payload["recovery_view"]["reasonCode"] == "settled_profit_truth_unavailable"
    assert payload["recovery_view"]["component"] == "receipt_outcome_truth"
    assert payload["recovery_view"]["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_repository_reasserts_canonical_lifecycle_fields_after_payload_overrides(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "is_degraded": False,
            "degraded_since_ts_ms": 0,
            "last_recovered_ts_ms": 999,
            "degraded_count": 0,
            "last_healthy_ts_ms": 999,
            "updated_ts_ms": 999,
            "history_status": "steady",
        },
    )
    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["component"] == "auto_trade_admission"
    assert persisted["is_degraded"] is True
    assert persisted["degraded_since_ts_ms"] == 1000
    assert persisted["last_recovered_ts_ms"] == 0
    assert persisted["degraded_count"] == 1
    assert persisted["last_healthy_ts_ms"] == 0
    assert persisted["updated_ts_ms"] == 1000
    assert persisted["history_status"] == "blocked"

    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        payload_extras={
            "is_degraded": True,
            "degraded_since_ts_ms": 1000,
            "last_recovered_ts_ms": 0,
            "degraded_count": 0,
            "last_healthy_ts_ms": 0,
            "updated_ts_ms": 1001,
            "history_status": "blocked",
        },
    )
    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["component"] == "auto_trade_admission"
    assert persisted["is_degraded"] is False
    assert persisted["degraded_since_ts_ms"] == 0
    assert persisted["last_recovered_ts_ms"] == 2000
    assert persisted["degraded_count"] == 1
    assert persisted["last_healthy_ts_ms"] == 2000
    assert persisted["updated_ts_ms"] == 2000
    assert persisted["history_status"] == "recovered"

    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)
    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery"]["history_status"] == "recovered"
    assert payload["history_items"][0]["historyStatus"] == "recovered"
    assert payload["history_items"][1]["historyStatus"] == "blocked"


def test_auto_trade_recovery_repository_reasserts_canonical_last_fields_after_payload_overrides(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={
            "last_reason_code": "ok",
            "last_stage": "ok",
            "last_blocker_component": "",
            "last_next_action": "",
            "last_reason_codes": [],
            "history_component": "receipt_outcome_truth",
            "history_stage": "fund_hold",
            "history_reason_code": "settled_profit_truth_unavailable",
            "history_reason_codes": ["settled_profit_truth_unavailable"],
            "history_status": "blocked",
            "reliability_class": "degraded",
            "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
            "reliability_reason_codes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "reliability_next_action": "restore_receipt_outcome_truth",
            "component_reliability_class": "fragile",
            "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
            "component_reliability_reason_codes": [
                "receipt_outcome_truth_reliability_fragile",
                "settled_profit_truth_unavailable",
            ],
            "component_reliability_next_action": "restore_receipt_outcome_truth",
            "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        },
    )
    persisted = runtime._repo.load("auto_trade_admission")
    assert persisted["last_stage"] == "fund_hold"
    assert persisted["last_reason_code"] == "settled_profit_truth_unavailable"
    assert persisted["last_blocker_component"] == "receipt_outcome_truth"
    assert persisted["last_next_action"] == "restore_receipt_outcome_truth"
    assert persisted["last_reason_codes"] == ["settled_profit_truth_unavailable"]

    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery_view"]["stage"] == "fund_hold"
    assert payload["recovery_view"]["reasonCode"] == "settled_profit_truth_unavailable"
    assert payload["recovery_view"]["component"] == "receipt_outcome_truth"
    assert payload["recovery_view"]["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_history_items_export_canonical_lifecycle_fields(tmp_path, monkeypatch):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="settled_profit_truth_unavailable",
        stage="fund_hold",
        blocker_component="receipt_outcome_truth",
        next_action="restore_receipt_outcome_truth",
        reason_codes=["settled_profit_truth_unavailable"],
        payload_extras={"degraded": False, "degraded_since_ts_ms": 0},
    )
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=False,
        ts_ms=2000,
        payload_extras={
            "degraded": True,
            "recovered_at_ts_ms": 0,
            "last_healthy_ts_ms": 0,
            "updated_ts_ms": 0,
        },
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    recovered = payload["history_items"][0]
    blocked = payload["history_items"][1]
    assert recovered["eventType"] == "recovered"
    assert recovered["degraded"] is False
    assert recovered["degradedSinceTsMs"] == 1000
    assert recovered["recoveredAtTsMs"] == 2000
    assert recovered["lastHealthyTsMs"] == 2000
    assert recovered["updatedTsMs"] == 2000
    assert blocked["eventType"] == "blocked"
    assert blocked["degraded"] is True
    assert blocked["degradedSinceTsMs"] == 1000
    assert blocked["recoveredAtTsMs"] == 0


def test_auto_trade_recovery_telemetry_route_derives_canonical_auto_trade_gate_from_blocked_recovery(
    tmp_path, monkeypatch
):
    runtime = _RecoveryTelemetryRuntime(str(tmp_path / "runtime.sqlite3"))
    runtime._repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1000,
        reason_code="capital_truth_unavailable",
        stage="fund_hold",
        blocker_component="fund_health",
        next_action="restore_capital_truth",
        reason_codes=["capital_truth_unavailable"],
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/telemetry/auto-trade-recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recovery"]["blocked"] is True
    assert payload["recovery_view"]["blocked"] is True
    assert payload["auto_trade_gate"] == {
        "allowed": False,
        "stage": "fund_hold",
        "reason_code": "capital_truth_unavailable",
        "reason_codes": ["capital_truth_unavailable"],
        "next_action": "restore_capital_truth",
    }
    assert payload["auto_trade_gate_view"] == {
        "allowed": False,
        "stage": "fund_hold",
        "reasonCode": "capital_truth_unavailable",
        "reasonCodes": ["capital_truth_unavailable"],
        "suggestedNextAction": "restore_capital_truth",
    }
