from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.state_service import (
    auto_trade_gate_info_from_recovery,
    auto_trade_recovery_info,
)
from victor_ai_bot.server import app


class _BlockedAuxRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 5,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "route_readiness",
            "history_stage": "route_hold",
            "history_reason_code": "route_truth_stale",
            "history_reason_codes": ["route_truth_stale", "execution_reality_unverified"],
            "history_next_action": "refresh_route_truth_before_resuming",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "route_truth_stale",
            "component_reliability_reason_codes": ["route_truth_stale"],
            "component_reliability_next_action": "refresh_route_truth_before_resuming",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _AuxRuntime:
    def __init__(self):
        self._auto_trade_recovery_repo = _BlockedAuxRecoveryRepo()

    def unified_state(self):
        return {"ok": True, "enabled": True, "source": "unified"}

    def spread_opportunities(self):
        return {"ok": True, "count": 2, "opps": [{"routeId": "r-1"}, {"routeId": "r-2"}]}

    def orchestrator_state(self):
        return {"ok": True, "enabled": True, "name": "orch"}

    def consensus_state(self):
        return {"ok": True, "last": {"block": 321}}

    def behaveagent_state(self):
        return {"ok": True, "enabled": True, "agent": "behave"}

    def governance_layer_state(self):
        return {"ok": True, "enabled": True, "threat": {"level": "low"}}

    def blockspace_state(self):
        return {"ok": True, "enabled": True, "mode": "private"}

    def agent_hub_state(self):
        return {"ok": True, "state": {"agents": 4}}


class _AuxRouteFailureRuntime:
    pass


def test_system_auxiliary_routes_surface_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _AuxRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    routes = {
        "/api/unified/state": ("source", "unified"),
        "/api/spread/opportunities": ("count", 2),
        "/api/orchestrator/state": ("name", "orch"),
        "/api/consensus/state": ("last", {"block": 321}),
        "/api/behaveagent/state": ("agent", "behave"),
        "/api/governance/state": ("threat", {"level": "low"}),
        "/api/blockspace/state": ("mode", "private"),
        "/api/agenthub/state": ("state", {"agents": 4}),
    }

    for route, (field, value) in routes.items():
        body = client.get(route).json()
        assert body["auto_trade_recovery"]["blocked"] is True
        assert body["auto_trade_recovery"]["history_component"] == "route_readiness"
        assert body["auto_trade_recovery"]["history_reason_code"] == "route_truth_stale"
        assert body["auto_trade_gate"] == {
            "allowed": False,
            "stage": "route_hold",
            "reason_code": "route_truth_stale",
            "reason_codes": ["route_truth_stale", "execution_reality_unverified"],
            "next_action": "refresh_route_truth_before_resuming",
        }
        assert body[field] == value


def test_system_auxiliary_routes_return_deterministic_error_payloads(monkeypatch):
    from victor_ai_bot.api_routes import system_routes

    client = TestClient(app)
    monkeypatch.setattr(app.state, "runtime", _AuxRouteFailureRuntime(), raising=False)

    monkeypatch.setattr(
        system_routes,
        "_unified_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("unified exploded")),
    )
    unified = client.get("/api/unified/state")

    monkeypatch.setattr(
        system_routes,
        "_spread_opportunities_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("spread exploded")),
    )
    spread = client.get("/api/spread/opportunities")

    monkeypatch.setattr(
        system_routes,
        "_orchestrator_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("orch exploded")),
    )
    orchestrator = client.get("/api/orchestrator/state")

    monkeypatch.setattr(
        system_routes,
        "_consensus_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("consensus exploded")),
    )
    consensus = client.get("/api/consensus/state")

    monkeypatch.setattr(
        system_routes,
        "_behaveagent_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("behave exploded")),
    )
    behaveagent = client.get("/api/behaveagent/state")

    monkeypatch.setattr(
        system_routes,
        "_governance_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("governance exploded")),
    )
    governance = client.get("/api/governance/state")

    monkeypatch.setattr(
        system_routes,
        "_blockspace_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("blockspace exploded")),
    )
    blockspace = client.get("/api/blockspace/state")

    monkeypatch.setattr(
        system_routes,
        "_agent_hub_state_payload",
        lambda rt: (_ for _ in ()).throw(RuntimeError("agenthub exploded")),
    )
    agenthub = client.get("/api/agenthub/state")

    recovery = auto_trade_recovery_info(None)
    gate = auto_trade_gate_info_from_recovery(recovery)

    assert unified.status_code == 200
    assert unified.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "unified_state_unavailable",
        "reason": "unified_state_unavailable",
        "error": "unified_state_failed",
        "enabled": False,
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert spread.status_code == 200
    assert spread.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "spread_opportunities_unavailable",
        "reason": "spread_opportunities_unavailable",
        "error": "spread_opportunities_failed",
        "count": 0,
        "opps": [],
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert orchestrator.status_code == 200
    assert orchestrator.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "orchestrator_state_unavailable",
        "reason": "orchestrator_state_unavailable",
        "error": "orchestrator_state_failed",
        "enabled": False,
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert consensus.status_code == 200
    assert consensus.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "consensus_state_unavailable",
        "reason": "consensus_state_unavailable",
        "error": "consensus_state_failed",
        "last": {},
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert behaveagent.status_code == 200
    assert behaveagent.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "behaveagent_state_unavailable",
        "reason": "behaveagent_state_unavailable",
        "error": "behaveagent_state_failed",
        "enabled": False,
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert governance.status_code == 200
    assert governance.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "governance_layer_unavailable",
        "reason": "governance_layer_unavailable",
        "error": "governance_layer_state_failed",
        "enabled": False,
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert blockspace.status_code == 200
    assert blockspace.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "blockspace_state_unavailable",
        "reason": "blockspace_state_unavailable",
        "error": "blockspace_state_failed",
        "enabled": False,
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }

    assert agenthub.status_code == 200
    assert agenthub.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "agent_hub_state_unavailable",
        "reason": "agent_hub_state_unavailable",
        "error": "agent_hub_state_failed",
        "state": {},
        "auto_trade_recovery": recovery,
        "auto_trade_gate": gate,
    }
