from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.wealth import router as wealth_router


class _BlockedRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 2,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "treasury_governance",
            "history_stage": "treasury_hold",
            "history_reason_code": "treasury_alignment_required",
            "history_reason_codes": [
                "treasury_alignment_required",
                "capital_truth_out_of_sync",
            ],
            "history_next_action": "realign_treasury_and_capital_truth",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "treasury_alignment_required",
            "component_reliability_reason_codes": ["treasury_alignment_required"],
            "component_reliability_next_action": "realign_treasury_and_capital_truth",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _Goal:
    def __init__(self):
        self.target_return_percentage = 8.0
        self.time_horizon_seconds = 14 * 86400
        self.risk_tolerance = "moderate"
        self.max_drawdown_pct = 12.0
        self.capital_commitment_pct = 35.0


class _TreasuryCfg:
    def __init__(self, goal):
        self.goal = goal


class _Treasury:
    def __init__(self, goal):
        self.cfg = _TreasuryCfg(goal)

    def snapshot(self):
        return {"aggressiveness": {"current_return_pct": 4.25}}


class _BlockedRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedRecoveryRepo()
        self._treasury = _Treasury(_Goal())
        self._wealth_goal_service = None
        self._cc = None


class _ExplodingWealthGoalService:
    def state(self, runtime):
        raise RuntimeError("wealth_goal_state_failed")


class _ExplodingRuntime:
    def __init__(self):
        self._treasury = _Treasury(_Goal())
        self._wealth_goal_service = _ExplodingWealthGoalService()
        self._cc = None


DEFAULT_RECOVERY = {
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

DEFAULT_GATE = {
    "allowed": True,
    "stage": "ok",
    "reason_code": "ok",
    "reason_codes": [],
    "next_action": "",
}


def test_wealth_goal_read_surface_projects_persisted_auto_trade_recovery_gate():
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _BlockedRuntime()
    client = TestClient(app)

    body = client.get("/api/wealth/goal").json()

    assert body["auto_trade_recovery"]["blocked"] is True
    assert body["auto_trade_recovery"]["history_component"] == "treasury_governance"
    assert body["auto_trade_gate"] == {
        "allowed": False,
        "stage": "treasury_hold",
        "reason_code": "treasury_alignment_required",
        "reason_codes": [
            "treasury_alignment_required",
            "capital_truth_out_of_sync",
        ],
        "next_action": "realign_treasury_and_capital_truth",
    }
    assert body["state"]["targetReturnPct"] == 8.0
    assert body["service"] == "wealth_goal_fallback"


def test_wealth_goal_read_surface_returns_deterministic_degraded_payload_when_builder_raises():
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _ExplodingRuntime()
    client = TestClient(app)

    body = client.get("/api/wealth/goal").json()

    assert body == {
        "ok": False,
        "status": "degraded",
        "reason_code": "wealth_goal_failed",
        "reason": "wealth_goal_failed",
        "error": "wealth_goal_failed",
        "goal": None,
        "state": {},
        "recommendation": {},
        "explanation": {},
        "history": [],
        "service": "wealth_goal_route",
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
