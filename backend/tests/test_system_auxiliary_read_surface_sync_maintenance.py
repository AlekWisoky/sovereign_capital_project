from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _MinimalSystemAuxRuntime:
    pass


class _AvailableSystemAuxRuntime:
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


def test_system_auxiliary_read_routes_fail_closed_when_runtime_capabilities_are_missing(
    monkeypatch,
):
    runtime = _MinimalSystemAuxRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    unified = client.get("/api/unified/state").json()
    spread = client.get("/api/spread/opportunities").json()
    orchestrator = client.get("/api/orchestrator/state").json()
    consensus = client.get("/api/consensus/state").json()
    behaveagent = client.get("/api/behaveagent/state").json()
    governance = client.get("/api/governance/state").json()
    blockspace = client.get("/api/blockspace/state").json()
    agenthub = client.get("/api/agenthub/state").json()

    assert unified["ok"] is False
    assert unified["status"] == "unavailable"
    assert unified["reason_code"] == "unified_state_unavailable"
    assert unified["enabled"] is False
    assert "auto_trade_recovery" in unified
    assert "auto_trade_gate" in unified

    assert spread["ok"] is False
    assert spread["status"] == "unavailable"
    assert spread["reason_code"] == "spread_opportunities_unavailable"
    assert spread["count"] == 0
    assert spread["opps"] == []

    assert orchestrator["ok"] is False
    assert orchestrator["reason_code"] == "orchestrator_state_unavailable"
    assert orchestrator["enabled"] is False

    assert consensus["ok"] is False
    assert consensus["reason_code"] == "consensus_state_unavailable"
    assert consensus["last"] == {}

    assert behaveagent["ok"] is False
    assert behaveagent["reason_code"] == "behaveagent_state_unavailable"
    assert behaveagent["enabled"] is False

    assert governance["ok"] is False
    assert governance["reason_code"] == "governance_layer_unavailable"
    assert governance["enabled"] is False

    assert blockspace["ok"] is False
    assert blockspace["reason_code"] == "blockspace_state_unavailable"
    assert blockspace["enabled"] is False

    assert agenthub["ok"] is False
    assert agenthub["reason_code"] == "agent_hub_state_unavailable"
    assert agenthub["state"] == {}


def test_system_auxiliary_read_routes_preserve_available_runtime_payloads(monkeypatch):
    runtime = _AvailableSystemAuxRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    unified = client.get("/api/unified/state").json()
    spread = client.get("/api/spread/opportunities").json()
    orchestrator = client.get("/api/orchestrator/state").json()
    consensus = client.get("/api/consensus/state").json()
    behaveagent = client.get("/api/behaveagent/state").json()
    governance = client.get("/api/governance/state").json()
    blockspace = client.get("/api/blockspace/state").json()
    agenthub = client.get("/api/agenthub/state").json()

    for body in (
        unified,
        spread,
        orchestrator,
        consensus,
        behaveagent,
        governance,
        blockspace,
        agenthub,
    ):
        assert "auto_trade_recovery" in body
        assert "auto_trade_gate" in body

    assert unified["source"] == "unified"
    assert spread["count"] == 2
    assert orchestrator["name"] == "orch"
    assert consensus["last"]["block"] == 321
    assert behaveagent["agent"] == "behave"
    assert governance["threat"]["level"] == "low"
    assert blockspace["mode"] == "private"
    assert agenthub["state"]["agents"] == 4
