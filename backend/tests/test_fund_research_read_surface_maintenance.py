from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.fund_service import FundService
from victor_ai_bot.server import app


class _ResearchReadRuntime:
    def research_pipeline_state(self):
        return {
            "items": [{"candidateId": "cand-1"}],
            "pipelineCounts": {"sandbox": 1},
            "throughput": {"researchHitRate": 0.25},
        }


def test_fund_research_candidates_route_uses_canonical_runtime_state(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _ResearchReadRuntime(), raising=False)
    client = TestClient(app)

    payload = client.get("/api/fund/research/candidates").json()

    assert payload["items"] == [{"candidateId": "cand-1"}]
    assert payload["pipelineCounts"] == {"sandbox": 1}
    assert payload["throughput"] == {"researchHitRate": 0.25}


def test_fund_service_research_pipeline_degrades_closed_when_workspace_snapshot_fails(monkeypatch):
    class _RuntimeWithoutResearchFacade:
        data_dir = "data"
        cfg = None

    def _boom(self):
        raise ValueError("corrupt workspace")

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.fund_service.ResearchWorkspace.snapshot",
        _boom,
    )

    summary = FundService().summary(_RuntimeWithoutResearchFacade())

    assert summary["researchPipeline"] == {"items": [], "pipelineCounts": {}, "throughput": {}}
