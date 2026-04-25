from __future__ import annotations

from victor_ai_bot.api_routes._route_helpers import auto_trade_route_projection


class _BlockedRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 2,
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
        return [{"reason_code": "private_lane_required", "stage": "route_hold"}]


class _Runtime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedRecoveryRepo()


def test_auto_trade_route_projection_defaults_include_recent_events_when_requested():
    projection = auto_trade_route_projection(include_recent_events=True)

    assert projection["auto_trade_recovery"]["blocked"] is False
    assert projection["auto_trade_recovery"]["recent_events"] == []
    assert projection["auto_trade_gate"] == {
        "allowed": True,
        "stage": "ok",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
    }


def test_auto_trade_route_projection_materializes_persisted_runtime_recovery():
    projection = auto_trade_route_projection(_Runtime(), include_recent_events=True)

    assert projection["auto_trade_recovery"]["blocked"] is True
    assert projection["auto_trade_recovery"]["history_component"] == "routing_quality"
    assert projection["auto_trade_recovery"]["recent_events"] == [
        {"reason_code": "private_lane_required", "stage": "route_hold"}
    ]
    assert projection["auto_trade_gate"] == {
        "allowed": False,
        "stage": "route_hold",
        "reason_code": "private_lane_required",
        "reason_codes": ["private_lane_required", "route_quality_unavailable"],
        "next_action": "restore_route_quality_and_private_lane",
    }


class _CapitalTruthRuntime:
    def fund_summary_state(self):
        return {
            "ok": True,
            "health": {
                "capitalTruthStatus": "degraded",
                "capitalTruthFreshnessClass": "stale",
                "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                "suggestedNextAction": "refresh_capital_truth_snapshot",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCodes": ["capital_truth_freshness_stale"],
                "recoveryNextAction": "refresh_capital_truth_snapshot",
            },
        }

    def capital_truth_state(self):
        return {
            "capitalContract": {
                "status": "blocked",
                "reason_code": "capital_truth_freshness_stale",
            }
        }


def test_auto_trade_route_projection_surfaces_capital_truth_health_for_runtime():
    projection = auto_trade_route_projection(_CapitalTruthRuntime(), include_recent_events=True)
    assert projection["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert projection["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert projection["capitalTruthHealth"]["stateContract"]["status"] == "blocked"
