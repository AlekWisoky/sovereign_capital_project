from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.runtime import RuntimeBundle
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
            "history_reason_codes": ["governance_review_required", "capital_truth_out_of_sync"],
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


class _FakeThreat:
    def snapshot(self):
        return {"level": "high", "code": "amber"}


class _FakeGov:
    def __init__(self):
        self.threat = _FakeThreat()

    def view_intent(self, *, intent_id: str):
        return {"ok": True, "intent": {"id": intent_id, "status": "pending"}}


class _RuntimeWithGovernance:
    def __init__(self):
        self._gov = _FakeGov()
        self._auto_trade_recovery_repo = _BlockedRecoveryRepo()


class _ExplodingGov:
    def __init__(self):
        self.threat = self

    def view_intent(self, *, intent_id: str):
        raise RuntimeError("intent_exploded")

    def snapshot(self):
        raise RuntimeError("threat_exploded")


class _ExplodingRuntime:
    def __init__(self):
        self._gov = _ExplodingGov()


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


def test_governance_read_routes_surface_persisted_auto_trade_recovery_gate():
    runtime = _RuntimeWithGovernance()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        intent = client.get("/api/governance/intent/intent-7").json()
        threat = client.get("/api/governance/threat_status").json()

        for body in (intent, threat):
            assert body["auto_trade_recovery"]["blocked"] is True
            assert body["auto_trade_recovery"]["history_component"] == "treasury_governance"
            assert body["auto_trade_gate"] == {
                "allowed": False,
                "stage": "fund_hold",
                "reason_code": "governance_review_required",
                "reason_codes": ["governance_review_required", "capital_truth_out_of_sync"],
                "next_action": "review_governance_and_capital_truth",
            }

        assert intent["intent"]["id"] == "intent-7"
        assert threat["threat"]["code"] == "amber"
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)


def test_governance_read_routes_return_deterministic_degraded_payloads():
    runtime = _ExplodingRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        intent = client.get("/api/governance/intent/intent-9").json()
        threat = client.get("/api/governance/threat_status").json()

        assert intent == {
            "ok": False,
            "status": "degraded",
            "reason_code": "governance_intent_failed",
            "reason": "governance_intent_failed",
            "error": "governance_intent_failed",
            "intent_id": "intent-9",
            "enabled": False,
            "auto_trade_recovery": DEFAULT_RECOVERY,
            "auto_trade_gate": DEFAULT_GATE,
        }

        assert threat == {
            "ok": False,
            "status": "degraded",
            "reason_code": "governance_threat_status_failed",
            "reason": "governance_threat_status_failed",
            "error": "governance_threat_status_failed",
            "enabled": False,
            "threat": {},
            "auto_trade_recovery": DEFAULT_RECOVERY,
            "auto_trade_gate": DEFAULT_GATE,
        }
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)
