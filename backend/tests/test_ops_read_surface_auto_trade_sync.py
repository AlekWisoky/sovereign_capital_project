from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.ops_routes import router as ops_router
from victor_ai_bot.runtime_services.state_service import (
    auto_trade_gate_info_from_recovery,
    auto_trade_recovery_info,
)


class _BlockedRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 2,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "routing_quality",
            "history_stage": "private_lane_required",
            "history_reason_code": "private_lane_required",
            "history_reason_codes": ["private_lane_required", "route_truth_stale"],
            "history_next_action": "restore_private_lane_and_refresh_route_truth",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "private_lane_required",
            "component_reliability_reason_codes": ["private_lane_required"],
            "component_reliability_next_action": "restore_private_lane_and_refresh_route_truth",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _BlockedRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedRecoveryRepo()

    def arbitrage_state(self):
        return {"ok": True, "enabled": True, "engine": "arb"}

    def mev_state(self):
        return {"ok": True, "enabled": True, "engine": "mev"}

    def meta_state(self):
        return {"ok": True, "enabled": True, "engine": "meta"}


class _ExplodingRuntime:
    def arbitrage_state(self):
        raise RuntimeError("arbitrage_state_failed")

    def mev_state(self):
        raise RuntimeError("mev_state_failed")

    def meta_state(self):
        raise RuntimeError("meta_state_failed")


DEFAULT_RECOVERY = auto_trade_recovery_info(None)
DEFAULT_GATE = auto_trade_gate_info_from_recovery(DEFAULT_RECOVERY)


def test_ops_read_routes_surface_persisted_auto_trade_recovery_gate():
    app = FastAPI()
    app.include_router(ops_router)
    app.state.runtime = _BlockedRuntime()
    client = TestClient(app)

    for path, engine in (
        ("/api/arbitrage/state", "arb"),
        ("/api/mev/state", "mev"),
        ("/api/meta/state", "meta"),
    ):
        body = client.get(path).json()
        assert body["engine"] == engine
        assert body["auto_trade_recovery"]["blocked"] is True
        assert body["auto_trade_recovery"]["history_component"] == "routing_quality"
        assert body["auto_trade_recovery"]["history_reason_code"] == "private_lane_required"
        assert body["auto_trade_gate"] == {
            "allowed": False,
            "stage": "private_lane_required",
            "reason_code": "private_lane_required",
            "reason_codes": ["private_lane_required", "route_truth_stale"],
            "next_action": "restore_private_lane_and_refresh_route_truth",
        }


def test_ops_read_routes_return_deterministic_degraded_payloads_when_state_builders_raise():
    app = FastAPI()
    app.include_router(ops_router)
    app.state.runtime = _ExplodingRuntime()
    client = TestClient(app)

    assert client.get("/api/arbitrage/state").json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "arbitrage_state_failed",
        "reason": "arbitrage_state_failed",
        "error": "arbitrage_state_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
    assert client.get("/api/mev/state").json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "mev_state_failed",
        "reason": "mev_state_failed",
        "error": "mev_state_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
    assert client.get("/api/meta/state").json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "meta_state_failed",
        "reason": "meta_state_failed",
        "error": "meta_state_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
