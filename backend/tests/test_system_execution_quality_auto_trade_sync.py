from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _BlockedSystemExecutionQualityRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 4,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "routing_quality",
            "history_stage": "route_hold",
            "history_reason_code": "private_lane_required",
            "history_reason_codes": ["private_lane_required", "route_quality_unavailable"],
            "history_next_action": "restore_route_quality_and_private_lane",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "private_lane_required",
            "component_reliability_reason_codes": ["private_lane_required"],
            "component_reliability_next_action": "restore_route_quality_and_private_lane",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _SystemExecutionQualityRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedSystemExecutionQualityRecoveryRepo()

    def execution_calibration_state(self):
        return {"items": [{"venue": "dex-a", "expected_edge_bps": 11.0}]}

    def venue_profiles_state(self):
        return {"venues": [{"venue": "dex-a", "reliability": "high"}]}

    def risk_memory_state(self):
        return {"failures": {"route-1": 1}}

    def path_diversity_state(self):
        return {"paths": [{"route_id": "route-1", "families": ["arb"]}]}

    def edge_learning_state(self):
        return {"items": [{"route_id": "route-1", "confidence": 0.92}]}

    def endpoint_quality_state(self):
        return {"summary": {"private": "preferred"}, "lanes": {}, "generatedAtMs": 123}

    def endpoint_universe_state(self):
        return {"private": {"candidates": [{"url": "rpc-fast"}]}}

    def venue_scorecards_state(self):
        return {"pairs": {"route-1": {"score": 0.88}}}

    def route_quality_state(self):
        return {"items": [{"route_id": "route-1", "quality": "high"}]}

    def execution_live_state(self):
        return {"items": [{"route_id": "route-1", "send_mode": "private"}]}

    def drawdown_state(self):
        return {"drawdownPct": 1.2}

    def kill_switch_state(self):
        return {"suppressed": []}


def test_system_execution_quality_surfaces_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _SystemExecutionQualityRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.get("/api/system/execution/quality")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["calibration"]["items"][0]["venue"] == "dex-a"
    assert body["route_quality"]["items"][0]["route_id"] == "route-1"
    assert body["live_execution"]["items"][0]["send_mode"] == "private"
    assert body["auto_trade_recovery"]["blocked"] is True
    assert body["auto_trade_recovery"]["history_component"] == "routing_quality"
    assert body["auto_trade_recovery"]["history_reason_code"] == "private_lane_required"
    assert body["auto_trade_gate"] == {
        "allowed": False,
        "stage": "route_hold",
        "reason_code": "private_lane_required",
        "reason_codes": ["private_lane_required", "route_quality_unavailable"],
        "next_action": "restore_route_quality_and_private_lane",
    }
