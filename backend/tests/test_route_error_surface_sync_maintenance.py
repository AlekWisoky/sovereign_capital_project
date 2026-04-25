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
    assert agent_state.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "agent_hub_state_failed",
        "reason": "agent_hub_state_failed",
        "error": "agent_hub_state_failed",
        "state": {},
        "attribution": {"agents": []},
        "weights": {},
    }

    attribution = client.get("/api/agents/attribution")
    assert attribution.status_code == 200
    assert attribution.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "agent_attribution_failed",
        "reason": "agent_attribution_failed",
        "error": "agent_attribution_failed",
        "agents": [],
    }

    scorecards = client.get("/api/strategies/scorecards")
    assert scorecards.status_code == 200
    assert scorecards.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "strategy_scorecards_failed",
        "reason": "strategy_scorecards_failed",
        "error": "strategy_scorecards_failed",
        "families": [],
    }

    evolution = client.get("/api/evolution/state")
    assert evolution.status_code == 200
    assert evolution.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "meta_state_failed",
        "reason": "meta_state_failed",
        "error": "meta_state_failed",
        "enabled": False,
    }

    candidates = client.get("/api/meta/candidates")
    assert candidates.status_code == 200
    assert candidates.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "meta_candidates_failed",
        "reason": "meta_candidates_failed",
        "error": "meta_candidates_failed",
        "items": [],
        "candidates": [],
    }
