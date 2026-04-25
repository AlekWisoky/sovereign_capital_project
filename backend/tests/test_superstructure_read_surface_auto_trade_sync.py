from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _BlockedRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 1,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "treasury_governance",
            "history_stage": "fund_hold",
            "history_reason_code": "governance_review_required",
            "history_reason_codes": [
                "governance_review_required",
                "capital_truth_out_of_sync",
            ],
            "history_next_action": "review_governance_and_capital_truth",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "governance_review_required",
            "component_reliability_reason_codes": ["governance_review_required"],
            "component_reliability_next_action": "review_governance_and_capital_truth",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _RuntimeWithSuperstructure:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedRecoveryRepo()

    def superstructure_state(self):
        return {
            "ok": True,
            "enabled": True,
            "agents": [{"id": "agent-1", "status": "running"}],
            "stability": {"score": 0.97, "status": "steady"},
        }

    def governance_state(self):
        return {"ok": True, "enabled": True, "threat": {"level": "low"}}

    def governance_health(self):
        return {"ok": True, "score": 0.92, "status": "green"}


class _ExplodingRuntime:
    def superstructure_state(self):
        raise RuntimeError("superstructure_exploded")

    def governance_state(self):
        raise RuntimeError("governance_state_exploded")

    def governance_health(self):
        raise RuntimeError("governance_health_exploded")


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


def test_superstructure_read_routes_surface_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _RuntimeWithSuperstructure()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    org = client.get("/api/org/state").json()
    stability = client.get("/api/org/stability").json()
    legacy_governance = client.get("/api/governance/state_legacy").json()
    governance_health = client.get("/api/governance/health").json()

    for body in (org, stability, legacy_governance, governance_health):
        assert body["auto_trade_recovery"]["blocked"] is True
        assert body["auto_trade_recovery"]["history_component"] == "treasury_governance"
        assert body["auto_trade_gate"] == {
            "allowed": False,
            "stage": "fund_hold",
            "reason_code": "governance_review_required",
            "reason_codes": ["governance_review_required", "capital_truth_out_of_sync"],
            "next_action": "review_governance_and_capital_truth",
        }

    assert org["agents"][0]["id"] == "agent-1"
    assert stability["stability"]["status"] == "steady"
    assert legacy_governance["threat"]["level"] == "low"
    assert governance_health["status"] == "green"


def test_superstructure_read_routes_return_deterministic_degraded_payloads(monkeypatch):
    runtime = _ExplodingRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    org = client.get("/api/org/state").json()
    stability = client.get("/api/org/stability").json()
    legacy_governance = client.get("/api/governance/state_legacy").json()
    governance_health = client.get("/api/governance/health").json()

    assert org == {
        "ok": False,
        "status": "degraded",
        "reason_code": "superstructure_state_failed",
        "reason": "superstructure_state_failed",
        "error": "superstructure_state_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }

    assert stability == {
        "ok": False,
        "status": "degraded",
        "reason_code": "superstructure_stability_failed",
        "reason": "superstructure_stability_failed",
        "error": "superstructure_stability_failed",
        "enabled": False,
        "stability": {},
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }

    assert legacy_governance == {
        "ok": False,
        "status": "degraded",
        "reason_code": "governance_state_legacy_failed",
        "reason": "governance_state_legacy_failed",
        "error": "governance_state_legacy_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }

    assert governance_health == {
        "ok": False,
        "status": "degraded",
        "reason_code": "governance_health_failed",
        "reason": "governance_health_failed",
        "error": "governance_health_failed",
        "enabled": False,
        "auto_trade_recovery": DEFAULT_RECOVERY,
        "auto_trade_gate": DEFAULT_GATE,
    }
