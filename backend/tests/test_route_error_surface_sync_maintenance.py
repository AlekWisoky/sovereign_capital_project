from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _RouteErrorRuntime:
    def agent_hub_state(self):
        raise LookupError("agent_state_missing")

    def agent_attribution_state(self):
        raise RuntimeError("attribution_unavailable")

    def strategy_scorecards_state(self):
        raise RuntimeError("scorecards_unavailable")

    def meta_state(self):
        raise RuntimeError("meta_state_unavailable")


def test_route_error_surface_returns_deterministic_degraded_payloads(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _RouteErrorRuntime(), raising=False)
    client = TestClient(app)

    agent_state = client.get("/api/agents/state")
    assert agent_state.status_code == 200
    agent_body = agent_state.json()
    agent_contract = agent_body.pop("summaryContract")
    assert agent_body == {"ok": False, "status": "degraded", "reason_code": "agent_hub_state_failed", "reason": "agent_hub_state_failed", "error": "agent_hub_state_failed", "state": {}, "attribution": {"agents": []}, "weights": {}}
    assert agent_contract["contractVersion"] == "canonical_summary_read_contract_v1"
    assert agent_contract["truthFamily"] == "agent_hub"
    assert agent_contract["readModel"] == "agent_hub_projection_v1"
    assert agent_contract["stateContract"]["reason_code"] == "agent_hub_state_failed"

    attribution = client.get("/api/agents/attribution")
    assert attribution.status_code == 200
    attribution_body = attribution.json()
    attribution_contract = attribution_body.pop("summaryContract")
    assert attribution_body == {"ok": False, "status": "degraded", "reason_code": "agent_attribution_failed", "reason": "agent_attribution_failed", "error": "agent_attribution_failed", "agents": []}
    assert attribution_contract["contractVersion"] == "canonical_summary_read_contract_v1"
    assert attribution_contract["truthFamily"] == "agent_attribution"
    assert attribution_contract["readModel"] == "agent_attribution_projection_v1"
    assert attribution_contract["stateContract"]["reason_code"] == "agent_attribution_failed"

    scorecards = client.get("/api/strategies/scorecards")
    assert scorecards.status_code == 200
    scorecards_body = scorecards.json()
    scorecards_contract = scorecards_body.pop("summaryContract")
    assert scorecards_body == {"ok": False, "status": "degraded", "reason_code": "strategy_scorecards_failed", "reason": "strategy_scorecards_failed", "error": "strategy_scorecards_failed", "families": []}
    assert scorecards_contract["contractVersion"] == "canonical_summary_read_contract_v1"
    assert scorecards_contract["truthFamily"] == "strategy_scorecards"
    assert scorecards_contract["readModel"] == "strategy_scorecards_projection_v1"
    assert scorecards_contract["stateContract"]["reason_code"] == "strategy_scorecards_failed"

    evolution = client.get("/api/evolution/state")
    assert evolution.status_code == 200
    evolution_body = evolution.json()
    evolution_contract = evolution_body.pop("summaryContract")
    assert evolution_body == {"ok": False, "status": "degraded", "reason_code": "meta_state_failed", "reason": "meta_state_failed", "error": "meta_state_failed", "enabled": False}
    assert evolution_contract["contractVersion"] == "canonical_summary_read_contract_v1"
    assert evolution_contract["truthFamily"] == "evolution_state"
    assert evolution_contract["readModel"] == "evolution_state_projection_v1"
    assert evolution_contract["stateContract"]["reason_code"] == "meta_state_failed"

    candidates = client.get("/api/meta/candidates")
    assert candidates.status_code == 200
    candidates_body = candidates.json()
    candidates_contract = candidates_body.pop("summaryContract")
    assert candidates_body == {"ok": False, "status": "degraded", "reason_code": "meta_candidates_failed", "reason": "meta_candidates_failed", "error": "meta_candidates_failed", "items": [], "candidates": []}
    assert candidates_contract["contractVersion"] == "canonical_summary_read_contract_v1"
    assert candidates_contract["truthFamily"] == "meta_candidates"
    assert candidates_contract["readModel"] == "meta_candidates_projection_v1"
    assert candidates_contract["stateContract"]["reason_code"] == "meta_candidates_failed"
