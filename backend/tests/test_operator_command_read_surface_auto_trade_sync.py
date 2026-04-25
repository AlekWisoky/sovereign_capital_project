from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.state_service import auto_trade_recovery_info
from victor_ai_bot.server import app


class _BlockedCommandRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 3,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "governance",
            "history_stage": "governance_hold",
            "history_reason_code": "manual_governance_review_required",
            "history_reason_codes": [
                "manual_governance_review_required",
                "operator_override_active",
            ],
            "history_next_action": "complete_governance_review",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "manual_governance_review_required",
            "component_reliability_reason_codes": ["manual_governance_review_required"],
            "component_reliability_next_action": "complete_governance_review",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _CommandRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedCommandRecoveryRepo()

    def superstructure_command_state(self):
        return {"ok": True, "mode": "steady", "enabled": True, "proposal_count": 1}


class _ExplodingCommandRuntime:
    def superstructure_command_state(self):
        raise RuntimeError("command_state_failed")


DEFAULT_RECOVERY = auto_trade_recovery_info(None)
DEFAULT_GATE = {
    "allowed": True,
    "stage": "ok",
    "reason_code": "ok",
    "reason_codes": [],
    "next_action": "",
}


def test_operator_command_state_surfaces_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _CommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    body = client.get("/api/command/state").json()

    assert body["ok"] is True
    assert body["mode"] == "steady"
    assert body["auto_trade_recovery"]["blocked"] is True
    assert body["auto_trade_recovery"]["history_component"] == "governance"
    assert body["auto_trade_gate"] == {
        "allowed": False,
        "stage": "governance_hold",
        "reason_code": "manual_governance_review_required",
        "reason_codes": [
            "manual_governance_review_required",
            "operator_override_active",
        ],
        "next_action": "complete_governance_review",
    }


def test_operator_command_state_returns_deterministic_degraded_payload(monkeypatch):
    runtime = _ExplodingCommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    body = client.get("/api/command/state").json()

    assert body["summaryContract"]["truthFamily"] == "operator_command_state"
    assert body["summaryContract"]["readModel"] == "operator_command_state_projection_v1"
    assert body["capitalTruthHealth"]["freshnessClass"] == "unknown"
    body.pop("summaryContract")
    body.pop("capitalTruthHealth")

    assert body == {
        "ok": False,
        "status": "degraded",
        "reason_code": "command_state_route_failed",
        "reason": "command_state_route_failed",
        "error": "command_state_route_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
