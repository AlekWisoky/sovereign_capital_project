from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _BlockedLaunchRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 3,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "rollout_readiness",
            "history_stage": "launch_hold",
            "history_reason_code": "launch_service_unavailable",
            "history_reason_codes": [
                "launch_service_unavailable",
                "family_hardening_restore_required",
            ],
            "history_next_action": "restore_launch_service_and_family_hardening",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "launch_service_unavailable",
            "component_reliability_reason_codes": ["launch_service_unavailable"],
            "component_reliability_next_action": "restore_launch_service_and_family_hardening",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _LaunchService:
    def summary(self, runtime):
        return {
            "ok": True,
            "mode": "FULL_MULTI_STRATEGY",
            "recommended_next_family": "funding_arb",
        }

    def family_detail(self, runtime, family: str):
        return {
            "ok": True,
            "family": family,
            "stage": "pilot_capital",
            "enabled": True,
        }


class _LaunchRuntime:
    def __init__(self):
        self._launch_service = _LaunchService()
        self._auto_trade_recovery_repo = _BlockedLaunchRecoveryRepo()

    def family_hardening_state(self):
        return {
            "ok": True,
            "items": [{"family": "funding_arb", "ready": True}],
            "recovery_status": "ready",
            "recovery_reliability_class": "stable",
        }


class _ExplodingLaunchService:
    def summary(self, runtime):
        raise RuntimeError("launch_summary_failed")

    def family_detail(self, runtime, family: str):
        raise RuntimeError("launch_detail_failed")


class _ExplodingLaunchRuntime:
    def __init__(self):
        self._launch_service = _ExplodingLaunchService()

    def family_hardening_state(self):
        return {
            "ok": True,
            "items": [{"family": "funding_arb", "ready": False}],
            "recovery_status": "ready",
            "recovery_reliability_class": "stable",
        }


def test_launch_read_routes_surface_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _LaunchRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    state = client.get("/api/launch/state").json()
    detail = client.get("/api/launch/family/funding_arb").json()

    for body in (state, detail):
        assert body["auto_trade_recovery"]["blocked"] is True
        assert body["auto_trade_recovery"]["history_component"] == "rollout_readiness"
        assert body["auto_trade_gate"] == {
            "allowed": False,
            "stage": "launch_hold",
            "reason_code": "launch_service_unavailable",
            "reason_codes": ["launch_service_unavailable", "family_hardening_restore_required"],
            "next_action": "restore_launch_service_and_family_hardening",
        }

    assert state["summaryContract"]["truthFamily"] == "launch"
    assert state["summaryContract"]["readModel"] == "launch_summary_projection_v1"
    assert state["mode"] == "FULL_MULTI_STRATEGY"
    assert detail["summaryContract"]["truthFamily"] == "launch_family"
    assert detail["summaryContract"]["readModel"] == "launch_family_projection_v1"
    assert detail["family"] == "funding_arb"
    assert detail["enabled"] is True


def test_launch_read_routes_return_deterministic_degraded_payloads(monkeypatch):
    runtime = _ExplodingLaunchRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    state = client.get("/api/launch/state").json()
    detail = client.get("/api/launch/family/funding_arb").json()

    assert state["ok"] is False
    assert state["summaryContract"]["truthFamily"] == "launch"
    assert state["summaryContract"]["readModel"] == "launch_summary_projection_v1"
    assert state["status"] == "degraded"
    assert state["reason_code"] == "launch_state_failed"
    assert state["reason"] == "launch_state_failed"
    assert state["error"] == "launch_state_failed"
    assert state["familyHardening"] == {
        "ok": True,
        "items": [{"family": "funding_arb", "ready": False}],
        "recovery_status": "ready",
        "recovery_reliability_class": "stable",
    }
    assert state["auto_trade_recovery"] == {
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
    }
    assert state["auto_trade_gate"] == {
        "allowed": True,
        "stage": "ok",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
    }
    assert state["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert state["capitalTruthHealth"]["stateContract"]["phase"] == "capital_truth_summary"

    assert detail["ok"] is False
    assert detail["summaryContract"]["truthFamily"] == "launch_family"
    assert detail["summaryContract"]["readModel"] == "launch_family_projection_v1"
    assert detail["status"] == "degraded"
    assert detail["reason_code"] == "launch_family_detail_failed"
    assert detail["reason"] == "launch_family_detail_failed"
    assert detail["error"] == "launch_family_detail_failed"
    assert detail["hardening"] == {
        "family": "funding_arb",
        "ready": False,
    }
    assert detail["auto_trade_recovery"] == {
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
    }
    assert detail["auto_trade_gate"] == {
        "allowed": True,
        "stage": "ok",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
    }
    assert detail["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert detail["capitalTruthHealth"]["stateContract"]["phase"] == "capital_truth_summary"
