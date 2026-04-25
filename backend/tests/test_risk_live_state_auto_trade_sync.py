from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _BlockedRiskRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 3,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "treasury_governance",
            "history_stage": "treasury_hold",
            "history_reason_code": "maximum_disabled",
            "history_reason_codes": ["maximum_disabled"],
            "history_next_action": "enable_maximum_or_reduce_aggressiveness",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "maximum_disabled",
            "component_reliability_reason_codes": ["maximum_disabled"],
            "component_reliability_next_action": "enable_maximum_or_reduce_aggressiveness",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _RiskLiveStateRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedRiskRecoveryRepo()

    def drawdown_state(self):
        return {"drawdownPct": 1.5, "hardStop": {"active": False, "reason_codes": []}}

    def kill_switch_state(self):
        return {"suppressed": []}

    def capital_engine_state(self):
        return {"ok": True, "available": "1000"}

    def endpoint_quality_state(self):
        return {"read": [{"ok": True}], "send": [{"ok": True}]}

    def endpoint_universe_state(self):
        return {"private": {"candidates": [{"url": "rpc-fast"}]}}

    def route_quality_state(self):
        return {"items": [{"route_id": "route-1", "quality": "high"}]}

    def execution_live_state(self):
        return {"items": [{"route_id": "route-1", "send_mode": "private"}]}


def test_risk_live_state_surfaces_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _RiskLiveStateRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.get("/api/risk/live-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["capital"]["available"] == "1000"
    assert body["route_quality"]["items"][0]["route_id"] == "route-1"
    assert body["live_execution"]["items"][0]["send_mode"] == "private"
    assert body["auto_trade_recovery"]["blocked"] is True
    assert body["auto_trade_recovery"]["history_component"] == "treasury_governance"
    assert body["auto_trade_recovery"]["history_reason_code"] == "maximum_disabled"
    assert body["auto_trade_gate"] == {
        "allowed": False,
        "stage": "treasury_hold",
        "reason_code": "maximum_disabled",
        "reason_codes": ["maximum_disabled"],
        "next_action": "enable_maximum_or_reduce_aggressiveness",
    }
