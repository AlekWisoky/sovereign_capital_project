from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _BlockedSystemControlSurfaceRecoveryRepo:
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


class _SystemControlSurfaceRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedSystemControlSurfaceRecoveryRepo()

    def service_health_state(self):
        return {"admission": {"status": "ok"}, "routing": {"status": "degraded"}}

    def capital_truth_state(self):
        return {"status": "ok", "equityUsd": 125000.0}

    def family_hardening_state(self):
        return {
            "status": "ok",
            "items": [{"family": "arb", "ready": True}],
            "recovery_status": "ready",
            "recovery_reliability_class": "stable",
        }

    def capital_explain(self):
        return {
            "ok": True,
            "status": "ready",
            "text": "capital truth synchronized",
            "facts": {"equityUsd": 125000.0},
            "causal": {"driver": "treasury_sync"},
        }


def test_system_control_routes_surface_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _SystemControlSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    services = client.get("/api/system/services").json()
    capital_truth = client.get("/api/system/capital/truth").json()
    family_hardening = client.get("/api/system/family-hardening").json()
    capital_explain = client.get("/api/system/capital/explain").json()

    for body in (services, capital_truth, family_hardening, capital_explain):
        assert body["auto_trade_recovery"]["blocked"] is True
        assert body["auto_trade_recovery"]["status"] == "treasury_alignment_required"
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

    assert services["admission"]["status"] == "ok"
    assert capital_truth["equityUsd"] == 125000.0
    assert family_hardening["items"][0]["family"] == "arb"
    assert capital_explain["text"] == "capital truth synchronized"
    assert capital_explain["facts"]["equityUsd"] == 125000.0
