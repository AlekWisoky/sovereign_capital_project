from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.treasury_extra import router as treasury_router
from victor_ai_bot.runtime import RuntimeBundle


class _BlockedTreasuryRecoveryRepo:
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


class _TreasuryRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedTreasuryRecoveryRepo()
        self._treasury = _Treasury(_Goal())

    def capital_engine_state(self):
        return {"ok": True, "equityUsd": 125000.0}

    def treasury_state(self):
        return {"ok": True, "allocator": "treasury", "enabled": True}


class _ExplodingTreasuryCfg:
    @property
    def goal(self):
        raise RuntimeError("goal_read_failed")


class _ExplodingTreasury:
    def __init__(self):
        self.cfg = _ExplodingTreasuryCfg()


class _ExplodingTreasuryRuntime:
    def __init__(self):
        self._treasury = _ExplodingTreasury()

    def capital_engine_state(self):
        raise RuntimeError("capital_failed")

    def treasury_state(self):
        raise RuntimeError("state_failed")


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


def test_treasury_read_routes_surface_persisted_auto_trade_recovery_gate():
    runtime = _TreasuryRuntime()
    app = FastAPI()
    app.include_router(treasury_router)
    app.state.runtime = runtime
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)

    capital = client.get("/api/treasury/capital").json()
    state = client.get("/api/treasury/state").json()
    goal = client.get("/api/treasury/goal").json()

    for body in (capital, state, goal):
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

    assert capital["equityUsd"] == 125000.0
    assert state["allocator"] == "treasury"
    assert goal["goal"]["target_return_pct"] == 8.0


def test_treasury_read_routes_return_deterministic_degraded_payloads():
    runtime = _ExplodingTreasuryRuntime()
    app = FastAPI()
    app.include_router(treasury_router)
    app.state.runtime = runtime
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)

    capital = client.get("/api/treasury/capital").json()
    state = client.get("/api/treasury/state").json()
    goal = client.get("/api/treasury/goal").json()

    assert capital == {
        "ok": False,
        "status": "degraded",
        "reason_code": "treasury_capital_failed",
        "reason": "treasury_capital_failed",
        "error": "treasury_capital_failed",
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }

    assert state == {
        "ok": False,
        "status": "degraded",
        "reason_code": "treasury_state_failed",
        "reason": "treasury_state_failed",
        "error": "treasury_state_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }

    assert goal == {
        "ok": False,
        "status": "degraded",
        "reason_code": "treasury_goal_failed",
        "reason": "treasury_goal_failed",
        "error": "treasury_goal_failed",
        "goal": None,
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
