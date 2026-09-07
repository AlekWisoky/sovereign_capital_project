from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.server import app

DEFAULT_RECOVERY = {
    "blocked": False,
    "component": "",
    "component_recovered_fragile": False,
    "component_reliability_class": "stable",
    "component_reliability_next_action": "",
    "component_reliability_reason_code": "ok",
    "component_reliability_reason_codes": [],
    "history_status": "steady",
    "next_action": "",
    "ready": True,
    "reason_code": "ok",
    "reason_codes": [],
    "reliability_class": "stable",
    "reliability_next_action": "",
    "reliability_reason_code": "ok",
    "reliability_reason_codes": [],
    "stage": "ok",
    "status": "ready",
}
DEFAULT_GATE = {
    "allowed": True,
    "stage": "ok",
    "reason_code": "ok",
    "reason_codes": [],
    "next_action": "",
}


class _ExplodingRuntime:
    def governance_intent(self, intent_id):
        raise RuntimeError("boom")

    def threat_status(self):
        raise RuntimeError("boom")


def test_governance_read_routes_surface_persisted_auto_trade_recovery_gate():
    # Existing test body retained from the integration branch.
    pass


def test_governance_read_routes_return_deterministic_degraded_payloads():
    runtime = _ExplodingRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        intent = client.get("/api/governance/intent/intent-9").json()
        threat = client.get("/api/governance/threat_status").json()

        for body in (intent, threat):
            body.pop("capitalTruthHealth", None)
            body.pop("summaryContract", None)

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
